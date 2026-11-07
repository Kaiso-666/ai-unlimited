"""Direct-API clients for DeepAI chat and FreeAnonymousAI.

Both providers are spoken to over their public JSON/form endpoints, not the UI.
No browser, no ads, no analytics, no client-side gating.

DeepAI   POST https://api.deepai.org/hacking_is_a_serious_crime   (yes, really)
AnonAI   POST https://www.freeanonymousai.com/api/generate

See PROTOCOL.md for the reverse-engineered wire format.
"""

from __future__ import annotations

import json
import math
import secrets
import string
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Iterator

DEEPAI_CHAT = "https://api.deepai.org/hacking_is_a_serious_crime"
DEEPAI_TASK = "https://api.deepai.org/check_chat_task_status"
DEEPAI_ORIGIN = "https://deepai.org"
ANON_CHAT = "https://www.freeanonymousai.com/api/generate"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) "
    "Gecko/20100101 Firefox/145.0"
)

M32 = 0xFFFFFFFF
SHIFTS = (7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21)


# --------------------------------------------------------------------------- #
# models (mirrored from the live picker, 2026-11)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Model:
    value: str
    label: str
    locked: bool = False          # Pro-only, enforced server-side
    super_genius: bool = False    # part of the "Super Genius" tier
    thinking: bool = False        # supports the thinking-task pipeline


MODELS: tuple[Model, ...] = (
    Model("standard", "Standard"),
    Model("genius", "Genius", locked=True),
    Model("supergenius", "Super Genius", locked=True, super_genius=True, thinking=True),
    Model("claude-opus-5-5", "Claude Opus 5.5", True, True, True),
    Model("gemini-4-argon", "Gemini 4 Argon", True, True, True),
    Model("gpt-6-astra", "GPT-6 Astra", True, True, True),
    Model("claude-fable-5", "Claude Fable 5", True, True, True),
    Model("gpt-6.1-sol", "GPT-6.1 Sol", True, False, True),
    Model("claude-haiku-5-5", "Claude Haiku 5.5"),
    Model("glm-5.3-flash", "GLM 5.3 Flash", False, False, True),
    Model("qwen3.8-flash", "Qwen 3.8 Flash"),
    Model("gemini-3.8-flash", "Gemini 3.8 Flash", True),
    Model("gpt-5.2", "GPT-5.2", True, False, True),
    Model("deepseek-v4.1-flash", "DeepSeek V4.1 Flash"),
    Model("grok-4.3", "Grok 4.3", True, False, True),
    Model("gpt-6-luna", "GPT-6 Luna"),
    Model("tencent-hy3", "Tencent Hy3"),
    Model("gemma-4", "Gemma 4"),
    Model("gpt-4.1", "GPT-4.1", True),
    Model("gpt-oss-120b", "GPT OSS 120B", False, False, True),
    Model("chatgpt-4o-latest", "ChatGPT 4o Latest", True),
    Model("llama-3.3-70b-instruct", "Llama 3.3 70B Instruct"),
    Model("llama-3.1-8b-instant", "Llama 3.1 8B Instant"),
    Model("llama-4-scout", "Llama 4 Scout", True),
)

MODEL_BY_VALUE = {m.value: m for m in MODELS}


class ProviderError(RuntimeError):
    """Upstream refused the request."""


class ModelLocked(ProviderError):
    """Model exists but the session is not entitled to it (DeepAI Pro gate)."""


class QuotaExceeded(ProviderError):
    """Per-identity message allowance is spent; retry with a fresh device id."""


# --------------------------------------------------------------------------- #
# DeepAI: island key (client-side signing the server does not verify, but the
# endpoint wants the shape `tryit-<random>-<hash>`)
# --------------------------------------------------------------------------- #

_K: tuple[int, ...] = tuple(
    int(4294967296.0 * math.sin(i % math.pi)) & M32 for i in range(1, 65)
)


def _hash(text: str) -> str:
    """Port of DeepAI's obfuscated MD5-shaped hash (custom K table)."""
    data = text.encode("utf-8")
    stream = list(data) + [0x80]
    n = len(stream) - 1

    c = (((n) // 4) + 2) | 15          # index of the bit-length word
    words: list[int] = [0] * (max(c, n >> 2) + 1)
    words[c - 1] = (8 * n) & M32

    for i in range(n, -1, -1):
        wi = i >> 2
        shift = (8 * i) & 31
        words[wi] = (words[wi] | ((stream[i] << shift) & M32)) & M32

    g = [1732584193, 4023233417, (~1732584193) & M32, (~4023233417) & M32]

    for block in range(0, c, 16):
        state = list(g)
        d, e = g[1], g[2]

        for i in range(64):
            a0, a3 = state[0], state[3]
            phase = i >> 4

            if phase == 0:
                f = (d & e) | ((~d & M32) & a3)
            elif phase == 1:
                f = (a3 & d) | ((~a3 & M32) & e)
            elif phase == 2:
                f = d ^ e ^ a3
            else:
                f = e ^ (d | ((~a3) & M32))
            f &= M32

            mi_tab = (i, 5 * i + 1, 3 * i + 5, 7 * i)
            mi = block | (mi_tab[phase] & 15)
            word = words[mi] if mi < len(words) else 0

            tmp = (a0 + f + _K[i] + word) & M32
            s = SHIFTS[4 * phase + (i % 4)]
            rot = (((tmp << s) & M32) | (tmp >> (32 - s))) & M32

            b_new = (d + rot) & M32
            state = [a3, b_new, d, e]
            d, e = b_new, d

        for i in range(4):
            g[i] = (g[i] + state[i]) & M32

    out = ""
    for i in range(32):
        # JS masks shift counts mod 32; Python does not.
        out += format((g[i >> 3] >> ((4 * (1 ^ i)) & 31)) & 15, "x")
    return out[::-1]


def island_key(user_agent: str = DEFAULT_UA) -> str:
    """Equivalent of the page's generateIslandKey()."""
    rnd = str(round(secrets.randbelow(10**11)))
    inner = _hash(user_agent + rnd + "hackers_become_a_little_stinkier_every_time_they_hack")
    h1 = _hash(user_agent + inner)
    h2 = _hash(user_agent + h1)
    return f"tryit-{rnd}-{h2}"


def new_device_id() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(43))


# --------------------------------------------------------------------------- #
# plumbing
# --------------------------------------------------------------------------- #

def _multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----hx" + secrets.token_hex(12)
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _open(url: str, data: bytes | None, headers: dict[str, str], timeout: int, opener=None):
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        if opener is None:
            return urllib.request.urlopen(req, timeout=timeout)
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"status": raw[:400]}
        status = str(payload.get("status", ""))
        if "only paid accounts" in status.lower():
            raise ModelLocked(status) from None
        if "try it exceeded" in status.lower() or "quota exceeded" in status.lower():
            raise QuotaExceeded(status) from None
        raise ProviderError(f"HTTP {exc.code}: {status or raw[:200]}") from None


# --------------------------------------------------------------------------- #
# DeepAI client
# --------------------------------------------------------------------------- #

class DeepAI:
    """Anonymous (or cookie-authenticated) DeepAI chat client.

    Free-tier models work with a throwaway `deepai_device_id`. If the server
    reports the per-identity allowance is spent, the client rotates the id and
    retries. Paid models raise ModelLocked -- that check is server-side and no
    payload mutation gets around it.
    """

    def __init__(
        self,
        device_id: str | None = None,
        cookie: str | None = None,
        user_agent: str = DEFAULT_UA,
        timeout: int = 180,
        retries: int = 3,
    ) -> None:
        self.device_id = device_id or new_device_id()
        self.cookie = cookie
        self.ua = user_agent
        self.timeout = timeout
        self.retries = retries
        self._jar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar)
        )

    # -- low level ---------------------------------------------------------

    def _headers(self, ua: str) -> dict[str, str]:
        headers = {
            "api-key": island_key(ua),
            "User-Agent": ua,
            "Origin": DEEPAI_ORIGIN,
            "Referer": DEEPAI_ORIGIN + "/chat",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        else:
            headers["Cookie"] = f"deepai_device_id={self.device_id}"
        return headers

    def _submit(self, fields: dict[str, str]) -> urllib.response.addinfourl:
        body, ctype = _multipart(fields)
        headers = self._headers(self.ua)
        headers["Content-Type"] = ctype
        return _open(DEEPAI_CHAT, body, headers, self.timeout, self._opener)

    # -- public API --------------------------------------------------------

    def chat(
        self,
        prompt: str,
        model: str = "standard",
        history: list[dict[str, str]] | None = None,
        thinking: bool | None = None,
        web_access: bool = False,
        sandbox: bool = False,
    ) -> Iterator[tuple[str, str]]:
        """Yield (`kind`, text) deltas. kind is "thinking" or "answer".

        Streaming endpoint returns raw UTF-8 text; thinking-capable models
        return a task id that is polled until COMPLETED.
        """
        meta = MODEL_BY_VALUE.get(model)
        if meta is None:
            raise ProviderError(f"unknown model {model!r}")

        use_thinking = meta.thinking if thinking is None else thinking
        messages = list(history or [])
        messages.append({"role": "user", "content": prompt})

        fields = {
            "chat_style": "chat",
            "language": "en",
            "chatHistory": json.dumps(messages, ensure_ascii=False),
            "model": model,
            "session_uuid": _uuid(),
            "sensitivity_request_id": _uuid(),
            "tool_activity_support": "1",
            "thinking_image_tool_support": "1",
            "hacker_is_stinky": "very_stinky",
            "enabled_tools": json.dumps(["image_generator", "image_editor"]),
            "memory_enabled": "false",
            "web_access_enabled": "true" if web_access else "false",
            "sandbox_enabled": "true" if sandbox else "false",
        }
        if use_thinking:
            fields["thinking_support"] = "1"

        attempt = 0
        while True:
            try:
                return (yield from self._run(fields, use_thinking))
            except QuotaExceeded:
                attempt += 1
                if attempt > self.retries:
                    raise
                if self.cookie:
                    raise ProviderError(
                        "quota exhausted on an authenticated session; rotating "
                        "device ids cannot reset an account allowance"
                    ) from None
                self.device_id = new_device_id()
                self._jar.clear()
                fields["session_uuid"] = _uuid()
                fields["sensitivity_request_id"] = _uuid()

    def _run(self, fields: dict[str, str], thinking: bool):
        resp = self._submit(fields)

        if thinking:
            raw = resp.read().decode("utf-8", "replace").strip()
            try:
                payload = json.loads(raw)
            except ValueError:
                yield ("answer", raw)
                return
            if not isinstance(payload, dict):
                yield ("answer", raw)
                return
            status = str(payload.get("status", ""))
            if "only paid accounts" in status.lower():
                raise ModelLocked(status)
            task_id = payload.get("task_id")
            if not task_id:
                yield ("answer", raw)
                return
            yield from self._poll(task_id)
            return

        seen_t = seen_a = 0
        while True:
            chunk = resp.read(2048)
            if not chunk:
                return
            text = chunk.decode("utf-8", "replace")
            head = text.lstrip()
            if head.startswith("{"):
                try:
                    payload = json.loads(text)
                except ValueError:
                    payload = None
                if isinstance(payload, dict) and "status" in payload and not payload.get("task_id"):
                    status = str(payload["status"])
                    if "only paid accounts" in status.lower():
                        raise ModelLocked(status)
                    if "exceeded" in status.lower():
                        raise QuotaExceeded(status)
            yield ("answer", text)
            seen_a += len(text)

    def _poll(self, task_id: str):
        last_t = last_a = ""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            headers = self._headers(self.ua)
            url = f"{DEEPAI_TASK}?type=thinking-task&task_id={task_id}"
            resp = _open(url, None, headers, 60, self._opener)
            data = json.loads(resp.read().decode("utf-8", "replace"))
            state = data.get("status")
            thinking = data.get("thinking_text") or ""
            answer = data.get("answer_text") or ""
            if thinking.startswith(last_t) and len(thinking) > len(last_t):
                yield ("thinking", thinking[len(last_t):])
                last_t = thinking
            if answer.startswith(last_a) and len(answer) > len(last_a):
                yield ("answer", answer[len(last_a):])
                last_a = answer
            if state in ("COMPLETED", "FAILED"):
                return
            time.sleep(1.2)
        raise ProviderError("thinking task timed out")

    def close(self) -> None:  # symmetry with other SDKs
        pass


# --------------------------------------------------------------------------- #
# FreeAnonymousAI client
# --------------------------------------------------------------------------- #

class FreeAnon:
    """Keyless proxy on freeanonymousai.com. No auth, no cookies, no signing."""

    def __init__(self, user_agent: str = DEFAULT_UA, timeout: int = 180) -> None:
        self.ua = user_agent
        self.timeout = timeout

    def chat(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        thinking: bool = False,
        search: bool = False,
        tool: str = "chat",
    ) -> Iterator[tuple[str, str]]:
        messages = list(history or [])
        messages.append({"role": "user", "content": prompt})
        payload: dict = {
            "prompt": prompt,
            "tool": tool,
            "attachments": [],
            "history": messages[:-1],
            "thinking": bool(thinking),
            "search": bool(search),
            "stream": True,
        }
        if model:
            payload["selectedModel"] = model

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.ua,
            "Origin": "https://www.freeanonymousai.com",
            "Referer": "https://www.freeanonymousai.com/chat/general",
            "Accept": "text/plain, application/json",
        }
        for attempt in range(4):
            try:
                resp = _open(ANON_CHAT, data, headers, self.timeout)
                break
            except ProviderError as exc:
                if "429" in str(exc) and attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise

        ctype = resp.headers.get("content-type", "")
        if "text/plain" in ctype:
            while True:
                chunk = resp.read(2048)
                if not chunk:
                    return
                yield ("answer", chunk.decode("utf-8", "replace"))
        raw = resp.read().decode("utf-8", "replace")
        try:
            obj = json.loads(raw)
        except ValueError:
            yield ("answer", raw)
            return
        out = obj.get("output") or obj.get("error") or raw
        yield ("answer", out)


# --------------------------------------------------------------------------- #
# Pollinations (the actual backend freeanonymousai.com falls back to)
# --------------------------------------------------------------------------- #

POLLINATIONS = "https://text.pollinations.ai"


class Pollinations:
    """Keyless OpenAI-compatible text API behind freeanonymousai.com.

    `GET /models` is authoritative for the anonymous tier; the wrapper site's
    `selectedModel` field is ignored by its own server, but here a model name
    is honoured for real.
    """

    def __init__(self, user_agent: str = DEFAULT_UA, timeout: int = 180) -> None:
        self.ua = user_agent
        self.timeout = timeout

    def models(self) -> list[dict]:
        resp = _open(f"{POLLINATIONS}/models", None, {"User-Agent": self.ua}, 30)
        return json.loads(resp.read().decode("utf-8", "replace"))

    def chat(
        self,
        prompt: str,
        model: str = "openai",
        history: list[dict[str, str]] | None = None,
        stream: bool = True,
    ) -> Iterator[tuple[str, str]]:
        messages = list(history or [])
        messages.append({"role": "user", "content": prompt})
        payload = json.dumps(
            {"model": model, "messages": messages, "stream": stream},
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.ua,
            "Accept": "text/event-stream, application/json",
            "Referer": "https://www.freeanonymousai.com/",
        }
        resp = _open(f"{POLLINATIONS}/openai", payload, headers, self.timeout)

        ctype = resp.headers.get("content-type", "")
        if "event-stream" not in ctype:
            raw = resp.read().decode("utf-8", "replace")
            try:
                obj = json.loads(raw)
            except ValueError:
                yield ("answer", raw)
                return
            msg = (obj.get("choices") or [{}])[0].get("message", {})
            if msg.get("reasoning"):
                yield ("thinking", msg["reasoning"])
            yield ("answer", msg.get("content") or "")
            return

        while True:
            line = resp.readline()
            if not line:
                return
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            delta = (obj.get("choices") or [{}])[0].get("delta", {})
            if delta.get("reasoning"):
                yield ("thinking", delta["reasoning"])
            if delta.get("content"):
                yield ("answer", delta["content"])


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())
