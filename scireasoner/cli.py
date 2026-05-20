"""SciReasoner CLI.

Examples
--------
$ scireasoner solve --problem "A 2 kg block slides down a 30° incline 5 m, μ=√3/10, g=10. Find speed at bottom."
$ scireasoner solve --problem-file p.txt --image figure.png
$ scireasoner caption --image figure.png --problem "..."
$ echo $? OPENAI_API_KEY=... scireasoner solve ...
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

from .pipeline import solve, caption, DEFAULT_MODEL


def _read_problem(args) -> str:
    if args.problem:
        return args.problem
    if args.problem_file:
        return Path(args.problem_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("error: provide --problem, --problem-file, or pipe text via stdin.")


def _common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--problem", help="Problem statement (text).")
    p.add_argument("--problem-file", help="Read problem text from a file.")
    p.add_argument("--image", help="Path to figure image (or omit for text-only).")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Model name (default: %(default)s).")
    p.add_argument("--api-key", default=None, help="API key (defaults to $OPENAI_API_KEY).")
    p.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (defaults to $OPENAI_BASE_URL).")
    p.add_argument("--json", dest="emit_json", action="store_true", help="Emit JSON instead of human text.")


def cmd_solve(args) -> int:
    problem = _read_problem(args)
    res = solve(
        problem=problem,
        image=args.image,
        use_critic=not args.no_critic,
        k_samples=args.k_samples,
        sc_temperature=args.sc_temperature,
        caption_model=args.model,
        reason_model=args.model,
        critic_model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
    )
    if args.emit_json:
        print(json.dumps({
            "answer": res.answer,
            "reasoning": res.reasoning,
            "caption": res.caption,
        }, ensure_ascii=False, indent=2))
    else:
        if res.caption:
            print("=== CAPTION ===")
            print(res.caption)
            print()
        print("=== REASONING ===")
        print(res.reasoning)
        print()
        print("=== ANSWER ===")
        print(res.answer)
    return 0


def cmd_caption(args) -> int:
    problem = ""
    if args.problem or args.problem_file:
        problem = _read_problem(args)
    if not args.image:
        raise SystemExit("error: caption requires --image.")
    cap = caption(problem=problem, image=args.image, model=args.model,
                  api_key=args.api_key, base_url=args.base_url)
    if args.emit_json:
        print(json.dumps({"caption": cap}, ensure_ascii=False, indent=2))
    else:
        print(cap or "(no caption — routed to direct-image path)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="scireasoner",
        description="SciReasoner — multimodal physics problem solving (1st place ICML 2025 SeePhys).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_solve = sub.add_parser("solve", help="End-to-end caption→reason→critic.")
    _common_args(sp_solve)
    sp_solve.add_argument("--no-critic", action="store_true", help="Skip the critic pass.")
    sp_solve.add_argument("--k-samples", type=int, default=1, help="Self-consistency vote count (>=2 enables SC).")
    sp_solve.add_argument("--sc-temperature", type=float, default=0.7)
    sp_solve.set_defaults(func=cmd_solve)

    sp_cap = sub.add_parser("caption", help="Run only the caption stage.")
    _common_args(sp_cap)
    sp_cap.set_defaults(func=cmd_caption)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
