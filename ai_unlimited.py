#!/usr/bin/env python3
"""ai-unlimited — direct-API chat clients for DeepAI / FreeAnonymousAI / Pollinations.

    python ai_unlimited.py models
    python ai_unlimited.py deepai "explain QUIC in 3 lines"
    python ai_unlimited.py deepai -i -m deepseek-v4.1-flash
    python ai_unlimited.py anon "hello"
    python ai_unlimited.py pollinations "hello" -m openai-fast

No browser, no ads, no client-side gates. See PROTOCOL.md for the wire format.
"""

from __future__ import annotations

import argparse
import sys

from providers import (
    MODELS,
    DeepAI,
    FreeAnon,
    ModelLocked,
    Pollinations,
    ProviderError,
    QuotaExceeded,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DIM = "\033[2m"
RED = "\033[31m"
GOLD = "\033[33m"
RESET = "\033[0m"


def emit(events, show_thinking: bool = True) -> str:
    """Print a provider event stream, return the accumulated answer."""
    answer = []
    in_thinking = False
    for kind, text in events:
        if kind == "thinking":
            if show_thinking:
                if not in_thinking:
                    sys.stdout.write(f"{DIM}[thinking] ")
                    in_thinking = True
                sys.stdout.write(text)
                sys.stdout.flush()
            continue
        if in_thinking:
            sys.stdout.write(f"{RESET}\n")
            in_thinking = False
        sys.stdout.write(text)
        sys.stdout.flush()
        answer.append(text)
    if in_thinking:
        sys.stdout.write(RESET)
    sys.stdout.write("\n")
    return "".join(answer)


def deepai_client(args) -> DeepAI:
    return DeepAI(
        device_id=args.device_id,
        cookie=args.cookie,
        user_agent=args.ua,
        timeout=args.timeout,
    )


def run_deepai(args, prompt: str, history: list[dict[str, str]]) -> str:
    client = deepai_client(args)
    thinking = True if args.thinking else (False if args.no_thinking else None)
    events = client.chat(
        prompt,
        model=args.model,
        history=history,
        thinking=thinking,
        web_access=args.web,
    )
    return emit(events, show_thinking=not args.quiet_thinking)


def run_anon(args, prompt: str, history: list[dict[str, str]]) -> str:
    client = FreeAnon(user_agent=args.ua, timeout=args.timeout)
    events = client.chat(
        prompt,
        history=history,
        thinking=args.thinking,
        search=args.search,
    )
    return emit(events, show_thinking=not args.quiet_thinking)


def run_pollinations(args, prompt: str, history: list[dict[str, str]]) -> str:
    client = Pollinations(user_agent=args.ua, timeout=args.timeout)
    events = client.chat(prompt, model=args.model, history=history)
    return emit(events, show_thinking=not args.quiet_thinking)


def repl(args, runner) -> None:
    history: list[dict[str, str]] = []
    if args.system:
        history.append({"role": "system", "content": args.system})
    print(f"{DIM}model={args.model} — empty line or Ctrl-D to quit{RESET}")
    while True:
        try:
            prompt = input(f"{GOLD}you>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not prompt:
            return
        try:
            answer = runner(args, prompt, history)
        except KeyboardInterrupt:
            print("\n[interrupted]")
            continue
        except ModelLocked as exc:
            print(f"{RED}locked:{RESET} {exc}")
            print(f"{DIM}this model is gated server-side; a Pro session is required{RESET}")
            continue
        except (ProviderError, QuotaExceeded) as exc:
            print(f"{RED}error:{RESET} {exc}")
            continue
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": answer})


def print_models() -> None:
    print(f"{'model':<24} {'label':<24} {'tier':<8} thinking")
    print("-" * 70)
    for m in MODELS:
        tier = "pro" if m.locked else "free"
        if m.super_genius:
            tier += "/sg"
        print(f"{m.value:<24} {m.label:<24} {tier:<8} {'yes' if m.thinking else ''}")
    print(f"\n{'free tier':<24} works anonymously")
    print(f"{'pro':<24} 401 'Only paid accounts can use genius' (server-side)")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-m", "--model", default="standard")
    common.add_argument("-i", "--interactive", action="store_true")
    common.add_argument("--system", default=None)
    common.add_argument("--thinking", action="store_true")
    common.add_argument("--no-thinking", action="store_true")
    common.add_argument("--quiet-thinking", action="store_true")
    common.add_argument("--ua", default=None)
    common.add_argument("--timeout", type=int, default=180)

    p = argparse.ArgumentParser(prog="ai_unlimited", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("models", help="list DeepAI models and their tier")

    d = sub.add_parser("deepai", parents=[common], help="DeepAI direct chat")
    d.add_argument("prompt", nargs="*")
    d.add_argument("--cookie", default=None, help="raw Cookie header (paid session)")
    d.add_argument("--device-id", default=None)
    d.add_argument("--web", action="store_true", help="enable web access")

    a = sub.add_parser("anon", parents=[common], help="freeanonymousai.com direct chat")
    a.add_argument("prompt", nargs="*")
    a.add_argument("--search", action="store_true")

    q = sub.add_parser("pollinations", parents=[common], help="Pollinations direct chat")
    q.add_argument("prompt", nargs="*")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "ua", None) is None:
        from providers import DEFAULT_UA

        args.ua = DEFAULT_UA

    if args.cmd == "models":
        print_models()
        return 0

    if args.cmd == "pollinations" and args.model == "standard":
        args.model = "openai-fast"

    runner = {
        "deepai": run_deepai,
        "anon": run_anon,
        "pollinations": run_pollinations,
    }[args.cmd]

    if args.interactive or not args.prompt:
        repl(args, runner)
        return 0

    prompt = " ".join(args.prompt)
    history: list[dict[str, str]] = []
    if args.system:
        history.append({"role": "system", "content": args.system})
    try:
        runner(args, prompt, history)
    except ModelLocked as exc:
        print(f"{RED}locked:{RESET} {exc}", file=sys.stderr)
        return 2
    except (ProviderError, QuotaExceeded) as exc:
        print(f"{RED}error:{RESET} {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
