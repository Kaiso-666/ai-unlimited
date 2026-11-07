#!/usr/bin/env python3
"""crack.py — static endpoint discovery + canary probe for "free AI, no login" sites.

    python crack.py sites.txt -o cracked.json
    python crack.py https://example.com/ --verbose

For each page it pulls the HTML, the same-origin JS bundles, extracts candidate
generation endpoints, then sends a canary prompt in a few common payload shapes
and records whatever comes back (status, content type, upstream model header).

No auth is guessed or brute-forced: this only reports what is reachable without
credentials, which is exactly the thing these sites advertise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) "
    "Gecko/20100101 Firefox/145.0"
)

ENDPOINT_RE = re.compile(
    r"""["'`](/(?:api|v1|chat|generate|ask|complete|completion|message|stream)[^"'`\s\\]{0,120})["'`]"""
)
ABS_RE = re.compile(
    r"""["'`](https?://[^"'`\s\\]{4,200}/(?:api|v1|chat|generate|ask|complete|completion)[^"'`\s\\]{0,120})["'`]"""
)
SCRIPT_RE = re.compile(r"""<script[^>]+src=["']([^"']+)["']""", re.I)
UPSTREAM_HINTS = (
    "pollinations", "openrouter", "groq", "together", "deepinfra", "fireworks",
    "huggingface", "mistral", "gemini", "openai", "anthropic",
)

PAYLOADS = (
    {"prompt": "Reply with exactly: OK", "stream": True},
    {"message": "Reply with exactly: OK"},
    {"messages": [{"role": "user", "content": "Reply with exactly: OK"}]},
    {"query": "Reply with exactly: OK"},
    {"prompt": "Reply with exactly: OK", "history": [], "stream": True},
)


def fetch(url: str, opener, data: bytes | None = None, ctype: str | None = None,
          timeout: int = 15, origin: str | None = None) -> tuple[int, dict, bytes]:
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
    }
    if origin:
        headers["Origin"] = origin
        headers["Referer"] = origin + "/"
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        resp = opener.open(req, timeout=timeout)
        return resp.status, dict(resp.headers), resp.read(400_000)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read(20_000)
    except Exception as exc:  # noqa: BLE001 - network noise is expected here
        return 0, {"x-error": str(exc)}, b""


def opener_for() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def discover(site: str, opener, verbose: bool) -> dict:
    status, headers, body = fetch(site, opener)
    html = body.decode("utf-8", "replace")
    out: dict = {
        "site": site,
        "page_status": status,
        "scripts": [],
        "endpoints": [],
        "upstream_hints": [],
        "probes": [],
    }
    if status == 0:
        out["error"] = headers.get("x-error")
        return out

    host = urlparse(site).netloc
    scripts = [urljoin(site, s) for s in SCRIPT_RE.findall(html)]
    scripts = [s for s in dict.fromkeys(scripts) if urlparse(s).netloc == host][:10]
    out["scripts"] = [s.split("?")[0] for s in scripts]

    blobs = [html]
    for src in scripts:
        st, _, sb = fetch(src, opener)
        if st == 200:
            blobs.append(sb.decode("utf-8", "replace"))

    endpoints: dict[str, int] = {}
    for blob in blobs:
        for match in ABS_RE.findall(blob):
            endpoints[match] = endpoints.get(match, 0) + 2
        for match in ENDPOINT_RE.findall(blob):
            endpoints[urljoin(site, match)] = endpoints.get(urljoin(site, match), 0) + 1
        for hint in UPSTREAM_HINTS:
            if hint in blob and hint not in out["upstream_hints"]:
                out["upstream_hints"].append(hint)

    ranked = sorted(endpoints.items(), key=lambda kv: (-kv[1], len(kv[0])))
    api_first = [u for u, _ in ranked if "/api" in u] + [u for u, _ in ranked if "/api" not in u]
    out["endpoints"] = api_first[:8]

    for endpoint in out["endpoints"][:3]:
        for payload in PAYLOADS:
            data = json.dumps(payload).encode()
            st, hdrs, rb = fetch(endpoint, opener, data, "application/json",
                                 timeout=25, origin=site.rstrip("/"))
            text = rb.decode("utf-8", "replace")
            if st == 0:
                continue
            model = (
                hdrs.get("X-Model") or hdrs.get("x-model")
                or (re.search(r'"model"\s*:\s*"([^"]+)"', text) or [None, None])[1]
            )
            record = {
                "endpoint": endpoint,
                "payload": list(payload),
                "status": st,
                "ctype": hdrs.get("Content-Type", ""),
                "model": model,
                "sample": text[:160].replace("\n", " "),
            }
            out["probes"].append(record)
            if verbose:
                print(f"  {st:>3} {endpoint} {list(payload)[0]} -> {record['sample'][:80]!r}")
            if st < 400 and text.strip():
                break
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", help="file with one URL per line, or a single URL")
    ap.add_argument("-o", "--out", default="cracked.json")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if args.targets.startswith("http"):
        sites = [args.targets]
    else:
        with open(args.targets, encoding="utf-8") as fh:
            sites = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]

    opener = opener_for()
    results = []
    for site in sites:
        print(f"[*] {site}")
        result = discover(site, opener, args.verbose)
        hits = [p for p in result["probes"] if p["status"] and p["status"] < 400]
        print(f"    endpoints={len(result['endpoints'])} live={len(hits)}"
              f" hints={','.join(result['upstream_hints']) or '-'}")
        results.append(result)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {args.out} ({len(results)} sites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
