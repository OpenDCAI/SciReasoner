"""Thin shell over the SeePhys Pro Codabench pipeline.

This module imports stage_caption / stage_reason / stage_critic from the
competition codebase at ``seephys_pro_codabench/scripts/run_v2.py``. It does
NOT modify that file — the goal is that prompt/strategy improvements made
during the live competition automatically flow through to anyone using the
public ``scireasoner`` API.
"""

from __future__ import annotations
import base64
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

# ----------------------------------------------------------------------------
# Wire the competition codebase into the import path *without* modifying it.
# ----------------------------------------------------------------------------
_PKG_ROOT = Path(__file__).resolve().parent.parent
_COMP_SCRIPTS = _PKG_ROOT / "seephys_pro_codabench" / "scripts"
if not _COMP_SCRIPTS.exists():
    raise ImportError(
        f"scireasoner expects competition pipeline at {_COMP_SCRIPTS}; not found. "
        "Install scireasoner from the SciReasoner repository root."
    )
if str(_COMP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_COMP_SCRIPTS))

import run_v2 as _run_v2  # noqa: E402

# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


@dataclass
class Result:
    """Result of an end-to-end ``solve()`` call."""

    answer: str
    reasoning: str
    caption: Optional[str]
    raw: dict  # full caption / reason / critic records for power users


# Default model selection mirrors the competition's best-config (sub_008).
DEFAULT_MODEL = os.environ.get("SCIREASONER_MODEL", "gemini-3.1-pro-preview")


def _load_image_to_dict(
    image: Optional[Union[str, bytes, Path]] = None,
    image_path: Optional[Union[str, Path]] = None,
    image_b64: Optional[str] = None,
) -> Optional[dict]:
    """Coerce an image input into the dict format expected by run_v2.get_images."""
    src = image if image is not None else (image_path if image_path else image_b64)
    if src is None:
        return None
    if isinstance(src, (str, Path)) and Path(str(src)).exists():
        return {"bytes": Path(str(src)).read_bytes(), "path": str(src)}
    if isinstance(src, bytes):
        return {"bytes": src, "path": None}
    if isinstance(src, str):  # treat as base64
        try:
            return {"bytes": base64.b64decode(src), "path": None}
        except Exception as e:
            raise ValueError(f"image string is not a valid path nor base64: {e}")
    raise TypeError(f"unsupported image type: {type(src).__name__}")


def _build_args(
    *,
    caption_model: str = DEFAULT_MODEL,
    reason_model: str = DEFAULT_MODEL,
    critic_model: str = DEFAULT_MODEL,
    use_critic: bool = True,
    k_samples: int = 1,
    sc_temperature: float = 0.7,
    max_tokens: int = 131072,
    timeout: float = 600.0,
    max_retries: int = 5,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> types.SimpleNamespace:
    """Build the argparse.Namespace shape that run_v2.stage_* expects."""
    return types.SimpleNamespace(
        caption_model=caption_model,
        reason_model=reason_model,
        critic_model=critic_model,
        use_critic=use_critic,
        k_samples=k_samples,
        sc_temperature=sc_temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
        api_key=api_key,
        base_url=base_url,
    )


def _build_row(
    problem: str,
    image_dict: Optional[dict] = None,
    qid: str = "scireasoner_inline",
) -> dict:
    """Build the row dict that run_v2.stage_* reads from."""
    images = [image_dict] if image_dict is not None else []
    return {
        "question_id": qid,
        "problem": problem or "",
        "images": images,
    }


def _make_client(api_key: Optional[str], base_url: Optional[str]):
    """Reuse run_v2's OpenAI client builder (handles env-var fallback)."""
    return _run_v2.make_client(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )


# ----------------------------------------------------------------------------
# Stage-level helpers (caption / reason / critic individually)
# ----------------------------------------------------------------------------


def caption(
    problem: str = "",
    image: Optional[Union[str, bytes, Path]] = None,
    *,
    qid: str = "scireasoner_inline",
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kw,
) -> Optional[str]:
    """Run only the caption stage. Returns the structured caption string,
    or None if the routing logic skips captioning (text-only problems)."""
    image_dict = _load_image_to_dict(image)
    row = _build_row(problem, image_dict, qid)
    args = _build_args(caption_model=model, api_key=api_key, base_url=base_url, **kw)
    client = _make_client(api_key, base_url)
    rec = _run_v2.stage_caption(client, args, row)
    return rec.get("caption")


def reason(
    problem: str,
    caption_text: Optional[str] = None,
    image: Optional[Union[str, bytes, Path]] = None,
    *,
    qid: str = "scireasoner_inline",
    model: str = DEFAULT_MODEL,
    k_samples: int = 1,
    sc_temperature: float = 0.7,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kw,
) -> dict:
    """Run only the reason stage. Returns the run_v2 reason record dict."""
    image_dict = _load_image_to_dict(image)
    row = _build_row(problem, image_dict, qid)
    args = _build_args(
        reason_model=model,
        k_samples=k_samples,
        sc_temperature=sc_temperature,
        api_key=api_key,
        base_url=base_url,
        **kw,
    )
    client = _make_client(api_key, base_url)
    return _run_v2.stage_reason(client, args, row, caption_text)


def critic(
    problem: str,
    candidate_answer: str,
    candidate_reasoning: str,
    caption_text: Optional[str] = None,
    image: Optional[Union[str, bytes, Path]] = None,
    *,
    qid: str = "scireasoner_inline",
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kw,
) -> dict:
    """Run only the critic stage. Returns the run_v2 critic record dict."""
    image_dict = _load_image_to_dict(image)
    row = _build_row(problem, image_dict, qid)
    args = _build_args(critic_model=model, api_key=api_key, base_url=base_url, **kw)
    client = _make_client(api_key, base_url)
    return _run_v2.stage_critic(
        client, args, row, caption_text, candidate_answer, candidate_reasoning
    )


# ----------------------------------------------------------------------------
# End-to-end one-shot solver
# ----------------------------------------------------------------------------


def solve(
    problem: str,
    image: Optional[Union[str, bytes, Path]] = None,
    *,
    qid: str = "scireasoner_inline",
    use_critic: bool = True,
    k_samples: int = 1,
    sc_temperature: float = 0.7,
    caption_model: str = DEFAULT_MODEL,
    reason_model: str = DEFAULT_MODEL,
    critic_model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kw,
) -> Result:
    """Solve a single physics problem end-to-end.

    Parameters
    ----------
    problem : str
        Problem statement text. May be empty for fully-visual L4-style problems.
    image : str | bytes | Path, optional
        Path to a figure file, raw bytes, or base64-encoded image data.
    use_critic : bool, default True
        Whether to run the critic+refine pass.
    k_samples : int, default 1
        Self-consistency vote count on the reason stage. ``k>1`` enables SC.

    Returns
    -------
    Result
        ``.answer``, ``.reasoning``, ``.caption``, plus full ``.raw`` records.
    """
    image_dict = _load_image_to_dict(image)
    row = _build_row(problem, image_dict, qid)
    args = _build_args(
        caption_model=caption_model,
        reason_model=reason_model,
        critic_model=critic_model,
        use_critic=use_critic,
        k_samples=k_samples,
        sc_temperature=sc_temperature,
        api_key=api_key,
        base_url=base_url,
        **kw,
    )
    client = _make_client(api_key, base_url)

    cap_rec = _run_v2.stage_caption(client, args, row)
    cap_text = cap_rec.get("caption")

    rea_rec = _run_v2.stage_reason(client, args, row, cap_text)
    cand_answer = rea_rec.get("chosen_answer", "") or ""
    cand_reasoning = rea_rec.get("chosen_reasoning", "") or ""

    final_ans, final_rea = cand_answer, cand_reasoning
    cri_rec = None
    if use_critic:
        cri_rec = _run_v2.stage_critic(
            client, args, row, cap_text, cand_answer, cand_reasoning
        )
        final_ans = cri_rec.get("answer") or cand_answer
        final_rea = cri_rec.get("reasoning") or cand_reasoning

    return Result(
        answer=final_ans.strip(),
        reasoning=(final_rea or "").strip(),
        caption=cap_text,
        raw={"caption": cap_rec, "reason": rea_rec, "critic": cri_rec},
    )
