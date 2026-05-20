"""MCP server exposing SciReasoner as tools to MCP-aware agents (Claude Code, Codex, Cursor, etc.).

Run directly:
    $ python -m scireasoner.mcp_server

Or via the installed entry-point:
    $ scireasoner-mcp

The server exposes three tools:
    * scireasoner_solve   — end-to-end caption→reason→critic on one problem
    * scireasoner_caption — only the caption stage (image → structured text)
    * scireasoner_reason  — reason stage given problem (+ optional caption)
"""

from __future__ import annotations
import os
import sys
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    sys.stderr.write(
        "error: scireasoner.mcp_server needs the `mcp` package.\n"
        "       pip install 'scireasoner[mcp]' or pip install mcp\n"
    )
    raise

from . import solve as _solve, caption as _caption, reason as _reason
from .pipeline import DEFAULT_MODEL

mcp = FastMCP("scireasoner")


@mcp.tool()
def scireasoner_solve(
    problem: str,
    image_path: Optional[str] = None,
    use_critic: bool = True,
    k_samples: int = 1,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Solve a physics problem end-to-end via caption → reason → critic.

    Parameters
    ----------
    problem : str
        Problem statement text. May be empty for fully-visual problems.
    image_path : str | None
        Absolute or relative path to a figure image (PNG / JPG). Omit for
        text-only problems.
    use_critic : bool, default True
        Whether to run the critic+refine pass after the initial answer.
    k_samples : int, default 1
        Self-consistency sample count on the reason stage. ``>=2`` enables
        majority-vote self-consistency.
    model : str, default ``gemini-3.1-pro-preview``
        OpenAI-compatible model name to use for all three stages. The
        endpoint is read from ``$OPENAI_BASE_URL``.

    Returns
    -------
    dict
        ``{"answer": str, "reasoning": str, "caption": str | null}``
    """
    res = _solve(
        problem=problem,
        image=image_path,
        use_critic=use_critic,
        k_samples=k_samples,
        caption_model=model,
        reason_model=model,
        critic_model=model,
    )
    return {
        "answer": res.answer,
        "reasoning": res.reasoning,
        "caption": res.caption,
    }


@mcp.tool()
def scireasoner_caption(
    image_path: str,
    problem: str = "",
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run only the caption stage on a figure.

    Returns a structured textual description suitable for passing into a
    downstream solver. Returns ``{"caption": null}`` when the routing logic
    decides the figure is unnecessary (rare for fully-visual problems).
    """
    cap = _caption(problem=problem, image=image_path, model=model)
    return {"caption": cap}


@mcp.tool()
def scireasoner_reason(
    problem: str,
    caption_text: Optional[str] = None,
    image_path: Optional[str] = None,
    k_samples: int = 1,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run only the reason stage. Useful when you already have a caption from
    a separate run, or want to chain custom captioning logic.

    Returns ``{"answer": str, "reasoning": str, "votes": int}``.
    """
    rec = _reason(
        problem=problem,
        caption_text=caption_text,
        image=image_path,
        k_samples=k_samples,
        model=model,
    )
    return {
        "answer": (rec.get("chosen_answer") or "").strip(),
        "reasoning": (rec.get("chosen_reasoning") or "").strip(),
        "votes": rec.get("votes", 0),
    }


def main() -> None:
    """Entry point — runs the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
