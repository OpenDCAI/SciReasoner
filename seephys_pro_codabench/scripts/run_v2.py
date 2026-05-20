#!/usr/bin/env python3
"""
SeePhys Pro v2 pipeline — adapts arxiv 2509.06079 (ICML 2025 SeePhys winner)
to SeePhys Pro and adds self-consistency voting.

Pipeline per question
---------------------
                                 +-------------+
   image  ---->  [STRUCTURED]    |             |
                 [CAPTIONER ]    |   IMAGE +   |   k=K samples
                       \\        |   CAPTION   |--->  [REASONER]  --->  parsed answer
                        \\------>|   (or only  |        x K
                                 |    image,   |          \\
                                 |    AAR)     |           v
                                 +-------------+      [VOTE / SC]
                                                          |
                                                          v
                                                     [CRITIC review]
                                                          |
                                                          v
                                                     final (pred, reasoning)

Stage outputs are cached per stage and per question_id under
output/<run>/cache/<stage>/<question_id>.json so a crash / Ctrl-C / network
hiccup never loses progress, and we can re-run any single stage.

Resume rules
------------
- Each stage writes one JSON file per question_id atomically (tmp+rename).
- A stage is "done" iff the cache file exists and its `ok` flag is true.
- Failed rows write a cache file with `ok: false` + error info, plus an entry
  in <run>/failures.jsonl. Re-running with --retry-failed reattempts those.
- A heartbeat file `<run>/heartbeat.json` is updated every N completions.

CLI
---
# Smoke (1 question per level, all 5 levels, testmini)
python scripts/run_v2.py --split testmini --limit-per-level 1 --run-name v2_smoke

# Full public leaderboard
python scripts/run_v2.py --split testmini --run-name v2_pub

# Full both
python scripts/run_v2.py --split both --run-name v2_full

# Re-run only failed rows
python scripts/run_v2.py --split testmini --retry-failed --run-name v2_pub

# Rebuild the CSV / submission.zip from cache without calling APIs
python scripts/run_v2.py --build-csv-only --run-name v2_pub
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import random
import re
import signal
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "SeePhysPro" / "data"
OUTPUT_DIR = ROOT / "output"

ALL_LEVELS = ["level1", "level2", "level3", "level4", "level5"]


# =============================================================================
# Domain routing (Adaptive Answer Routing) — these domains skip caption
# Source: arxiv 2509.06079, Sec. on Adaptive Answer Routing
# =============================================================================

DIRECT_IMAGE_KEYWORDS = [
    # quantum
    r"\bquantum\b", r"wavefunction", r"schr[öo]dinger", r"\bspin\b", r"\bqubit\b",
    # projectile / mechanics with trajectory
    r"projectile", r"trajectory", r"parabolic motion",
    # electromagnetic fields
    r"electromagnetic field", r"\bemf\b", r"magnetic flux", r"\bsolenoid\b",
    # charge distribution
    r"charge distribution", r"point charge", r"gauss(?:ian|'s) law", r"electric flux",
    # circuits
    r"\bcircuit\b", r"\bresistor", r"\bcapacitor", r"\bbattery\b", r"\bohm",
    r"kirchhoff", r"\bvoltage\b", r"\bcurrent\b",
    # spring force
    r"\bspring\b", r"hooke", r"oscillat",
    # atomic
    r"\batomic\b", r"\bbohr\b", r"hydrogen-like", r"emission spectrum",
]
DIRECT_IMAGE_RE = re.compile("|".join(DIRECT_IMAGE_KEYWORDS), re.IGNORECASE)


def route_use_caption(problem: str) -> bool:
    """Return True iff captioning helps. False => direct image only."""
    if not problem:
        return True
    return DIRECT_IMAGE_RE.search(problem) is None


# =============================================================================
# Prompts
# =============================================================================

CAPTION_SYSTEM = (
    "You are a meticulous physics-diagram analyst. Given a physics problem image, "
    "extract every detail that a solver might need: labeled points, vectors, fields, "
    "values, axes, regions, geometric relations, and any text inside the figure."
)

CAPTION_USER = """\
Below is a physics problem. Look at the attached figure and produce a STRUCTURED caption.

PROBLEM TEXT (for context — do not solve yet):
{problem}

Return ONLY the caption in the following template (fill what applies, omit empty bullets):

[FIGURE TYPE]: <e.g., free-body diagram, circuit, optics ray diagram, EM-field map, ...>

[OBJECTS / BODIES]:
- <name>: <position, dimensions, labels, role>

[FORCES / VECTORS]:
- <symbol>: <magnitude if shown, direction, point of application>

[FIELDS / REGIONS]:
- <name>: <type, magnitude/sign if shown, spatial extent>

[GEOMETRY]:
- <axes, distances, angles, coordinate origins, lengths in symbols or numerical>

[LABELS / IN-IMAGE TEXT]:
- <verbatim transcription of any text/numbers/symbols visible in the figure>

[CONSTRAINTS / REFERENCE STATES]:
- <e.g., "rod is initially at rest", "switch open", "ground at infinity">

[NOTES]:
- <anything subtle that isn't obvious from text alone>

Be exact. Do NOT solve the problem. Do NOT speculate beyond the figure.
"""

# =============================================================================
# L4 (fully visual) caption — text field is empty, the entire problem is in the image.
# This template forces aggressive verbatim OCR of question stem + options + values.
# =============================================================================
L4_CAPTION_USER = """\
This is a fully-visual physics problem: there is NO accompanying text — the entire
question, all numerical values, and all options are inside the image.

Your job is to transcribe and structure the image so that another solver who CANNOT see
the image could solve it from your caption alone. Be exhaustive. Do NOT solve. Do NOT
speculate beyond what is visible. Transcribe Chinese verbatim if Chinese; English if
English.

Return ONLY the caption in this template (fill every section that applies; mark a
section "—" if truly empty):

[QUESTION STEM (verbatim)]:
<full transcription of the problem statement, in the language used in the figure.
Preserve numbering of sub-questions like (1), (2), (a), (b). Do NOT paraphrase.>

[GIVEN VALUES]:
- <symbol>: <numeric value with units, e.g. "m = 2 kg", "B = 0.5 T", "θ = 30°">
- ... (one per line; include EVERY constant, mass, length, angle, voltage, etc. shown)

[FIGURE TYPE]: <free-body diagram | circuit | optics ray diagram | EM-field map |
kinematics trajectory | thermodynamic process | graph/plot | mixed | other>

[OBJECTS / BODIES]:
- <name>: <position, dimensions, labels, role>

[FORCES / VECTORS]:
- <symbol>: <magnitude if shown, direction, point of application>

[FIELDS / REGIONS]:
- <name>: <type, magnitude/sign, spatial extent>

[GEOMETRY]:
- <axes, distances, angles, coordinate origins, lengths in symbols or numerical>

[GRAPHS / PLOTS]:
- <horizontal axis: quantity, units, marked tick values>
- <vertical axis: quantity, units, marked tick values>
- <curve(s): shape, key points, slopes, intercepts, equations if shown>

[OPTIONS (verbatim)]:
A) <full text of option A as printed in image>
B) <full text of option B>
C) <full text of option C>
D) <full text of option D>
(If not multiple choice, write "[OPTIONS]: not applicable".)

[SUB-QUESTIONS]:
(1) <verbatim>
(2) <verbatim>
...

[CONSTRAINTS / REFERENCE STATES]:
- <e.g., "rod is initially at rest", "switch open", "ground at infinity">

[NOTES]:
- <anything subtle that isn't obvious from text alone>

CRITICAL: the [QUESTION STEM (verbatim)] section is required and must be a faithful
transcription of every line of problem text visible in the image. Missing text in the
stem will cause the downstream solver to fail.
"""

# =============================================================================
# L2 / L3 caption — text+image. Same family as default but adds explicit
# verbatim sections for in-image numerical values, graph data, and any options
# or sub-questions printed inside the figure. Designed to address the L4
# success pattern in a hybrid form: text remains primary context, but the
# image is treated as a first-class source of detail rather than supplementary.
# =============================================================================
L23_CAPTION_USER = """\
Below is a physics problem with both text and a figure. Your job is to produce a
STRUCTURED caption that fully exposes every detail visible in the figure so that
a downstream solver, who already has the problem text below, can rely on your
caption (plus the original image) for ALL in-image content.

PROBLEM TEXT (context — already given to the solver, do NOT solve, do NOT paraphrase):
{problem}

Return ONLY the caption in this template (fill every section that applies; mark a
section "—" if truly empty):

[FIGURE TYPE]: <free-body diagram | circuit | optics ray diagram | EM-field map |
kinematics trajectory | thermodynamic process | graph/plot | waveform | mixed | other>

[OBJECTS / BODIES]:
- <name>: <position, dimensions, labels, role>

[FORCES / VECTORS]:
- <symbol>: <magnitude if shown, direction, point of application>

[FIELDS / REGIONS]:
- <name>: <type, magnitude/sign if shown, spatial extent>

[GEOMETRY]:
- <axes, distances, angles, coordinate origins, lengths in symbols or numerical>

[GIVEN VALUES IN IMAGE]:
- <symbol>: <numeric value with units, e.g. "L = 2 m", "θ = 30°", "B₀ = 0.5 T">
- (Include EVERY labeled numeric value visible in the figure — masses, charges,
  capacitances, resistances, voltages, lengths, angles, field strengths, tick
  values on axes, etc. If a value is also in the problem text, list it here once.
  Mark "—" if truly no in-image numerics.)

[GRAPHS / PLOTS]:
- <horizontal axis: quantity, units, marked tick values>
- <vertical axis: quantity, units, marked tick values>
- <curve(s): shape, key points (x,y), slopes, intercepts, equations if shown>
- (Mark "—" if not a plot/waveform.)

[OPTIONS / LABELS IN IMAGE (verbatim)]:
- <if the figure labels distinct curves/trajectories/regions as A/B/C/D, or
  embeds option text, transcribe each label verbatim with its visual location>
- (Mark "—" if not present. Do NOT copy options from the problem text — they
  belong only here when printed inside the image.)

[IN-IMAGE TEXT / ANNOTATIONS]:
- <verbatim transcription of any other words/numbers/symbols visible in the
  figure, in the original language (Chinese verbatim if Chinese)>

[CONSTRAINTS / REFERENCE STATES]:
- <e.g., "rod is initially at rest", "switch open", "ground at infinity">

[NOTES]:
- <anything subtle that isn't obvious from text alone, e.g. arrow conventions,
  shading, dashed vs solid lines, hidden symmetries>

CRITICAL: the [GIVEN VALUES IN IMAGE], [GRAPHS / PLOTS], and [OPTIONS / LABELS
IN IMAGE] sections must be exhaustive when applicable. Missing in-image numbers
or curve data is the most common failure mode. Be exact. Do NOT solve. Do NOT
speculate beyond what the figure shows.
"""

REASONER_SYSTEM = (
    "You are an expert physics problem solver competing in a graded benchmark. "
    "You receive a problem text, optionally a structured caption of any figure, "
    "and the figure itself when available. Reason rigorously with explicit physics "
    "and math. Track units. Be careful with signs, limits, and special cases. "
    "Submit a concise, parseable final answer."
)

REASONER_USER = """\
=== PROBLEM ===
{problem}

{caption_block}

INSTRUCTIONS
1) Restate what is given and what is asked, in your own words.
2) Identify the relevant physical principles and which equations apply.
3) Solve step by step. Show key intermediate quantities and units.
4) State the final answer in the most natural form (number, expression, units, or option letters like "BD").
5) Wrap your output STRICTLY as:
<reasoning>
... full chain of reasoning ...
</reasoning>
<answer>... final answer only — no extra words ...</answer>

If the problem is multiple-choice, the <answer> must be the letter(s) only, e.g. "BD".
If a numerical answer is needed and the question asks for a unit, include it.
"""

# NOTE 2026-05-19: a v3 "strict format rules" prompt was tested (forbid hedging, keep
# natural units, canonical LaTeX, etc.) and submitted as sub_005. It changed 40/200 L1
# answers but L1 score stayed the same (0.765) — judge is form-tolerant. Reverted to
# the simpler prompt above. Lesson: don't tighten format rules; attack reasoning
# quality (SC k=3, few-shot) instead.

# NOTE 2026-05-20: SC k=3 @ T=0.7 on L1 was tested (sub_006). 75% of L1 already
# converges 3-0 unanimous, so SC has no headroom. L1 went 0.765 → 0.760 (−1q,
# net loss). Confirmed: L1 needs prompt content changes (worked examples,
# domain routing), not sampling diversity.

# =============================================================================
# L1 (text-only) — few-shot REASONER prompt with worked physics examples.
# Goal: show the model the *style of reasoning* that performs well on this
# benchmark (clear given/asked, named physical principle, careful unit
# tracking, parseable final answer in canonical form). The 3 examples cover
# mechanics+friction, EM (circuit), and multichoice physics, which are the
# dominant L1 sub-domains.
#
# Used only when route_use_caption() returns False (= text-only level, mostly
# L1). For L2-L5, the original REASONER_USER continues to apply.
# =============================================================================
REASONER_USER_L1_FEWSHOT = """\
You will solve a physics problem. First, here are three worked examples that
demonstrate the rigor and final-answer style we expect.

=== WORKED EXAMPLE 1 (mechanics, energy + friction) ===
PROBLEM: A block of mass m = 2 kg starts from rest at the top of a fixed incline
of angle θ = 30° and slides distance L = 5 m along the incline. The coefficient
of kinetic friction is μ = √3/10. Take g = 10 m/s². Find the speed at the bottom.

<reasoning>
Given: m=2 kg, θ=30°, L=5 m, μ=√3/10, g=10 m/s², initial speed v₀=0.
Asked: speed v at the bottom of the incline.
Principle: work-energy theorem along the incline.
- Component of gravity along the incline: mg sin θ
- Normal force: N = mg cos θ
- Friction (kinetic, opposing motion up the incline → here the block slides down,
  so friction acts up the incline): f = μ N = μ mg cos θ
- Net force along the incline (down-slope positive): F_net = mg sin θ − μ mg cos θ
- Work done by net force over L: W = F_net · L = mg L (sin θ − μ cos θ)
- Energy balance: ½ m v² − 0 = W ⇒ v = √(2 g L (sin θ − μ cos θ))

Plugging in: sin 30° = 1/2, cos 30° = √3/2, μ cos θ = (√3/10)(√3/2) = 3/20.
sin θ − μ cos θ = 1/2 − 3/20 = 10/20 − 3/20 = 7/20.
v = √(2 · 10 · 5 · 7/20) = √(35) ≈ 5.92 m/s.
</reasoning>
<answer>\\sqrt{{35}}\\,\\mathrm{{m/s}}</answer>

=== WORKED EXAMPLE 2 (EM, RC discharge) ===
PROBLEM: A capacitor of capacitance C is charged to initial voltage V₀ and at
t=0 connected through a switch to a resistor R. Find the time t at which the
energy stored in the capacitor falls to one quarter of its initial value.

<reasoning>
Given: capacitance C, initial voltage V₀, series resistance R; switch closed at t=0.
Asked: time t such that the stored energy U(t) = U(0)/4.
Principle: RC discharge with τ = RC. Voltage decays as V(t) = V₀ e^{{−t/τ}}.
Energy in capacitor: U(t) = ½ C V(t)² = ½ C V₀² e^{{−2t/τ}}.
Condition U(t) = U(0)/4 ⇒ e^{{−2t/τ}} = 1/4 ⇒ −2t/τ = −ln 4 = −2 ln 2.
Therefore t = τ ln 2 = RC ln 2.
</reasoning>
<answer>RC \\ln 2</answer>

=== WORKED EXAMPLE 3 (multiple choice, mechanics) ===
PROBLEM: A particle moves in one dimension under a conservative force. Its
potential energy U(x) has a single local minimum at x₀ and U → +∞ as |x| → ∞.
Which of the following statements about motion with total energy E (where U(x₀) <
E < ∞) MUST be true? (A) The motion is periodic. (B) The kinetic energy is
maximum at x₀. (C) The particle reaches arbitrarily large |x|. (D) The motion
is simple harmonic.

<reasoning>
- (A) Energy E > U(x₀) and U → +∞ both ways ⇒ classically allowed region is
  bounded, with two turning points. Motion oscillates between them ⇒ periodic. TRUE.
- (B) KE = E − U(x). U is minimum at x₀ ⇒ KE is maximum at x₀. TRUE.
- (C) Allowed region is bounded by turning points where U = E (finite |x|),
  so the particle does NOT reach arbitrarily large |x|. FALSE.
- (D) SHM requires U quadratic. A general well is only approximately quadratic
  near the minimum, not necessarily SHM globally. FALSE.
Therefore the correct statements are A and B.
</reasoning>
<answer>AB</answer>

=== END OF EXAMPLES ===

Now solve the actual problem below using the same style: restate given/asked,
name the physical principle, derive step by step, give a clean final answer
in the most natural canonical form. Wrap your output STRICTLY as
<reasoning>...</reasoning><answer>...</answer>.

For multiple-choice problems, the <answer> must be the letter(s) only (e.g. "BD").
For numerical problems, include the unit if the question asks for one.

=== PROBLEM ===
{problem}

{caption_block}
"""

CRITIC_SYSTEM = (
    "You are a senior physics professor performing a rigorous critical review. "
    "Given a problem, optional figure, structured caption, and a candidate solution, "
    "decide whether the candidate's final answer is correct. If wrong, produce the "
    "correct one. Be especially attentive to units, signs, edge cases, and to "
    "whether the reasoning actually supports the stated answer."
)

CRITIC_USER = """\
=== PROBLEM ===
{problem}

{caption_block}

=== CANDIDATE SOLUTION ===
<reasoning>
{cand_reasoning}
</reasoning>
<answer>{cand_answer}</answer>

TASK
- Verify the candidate's reasoning step by step.
- Check units, signs, limits, and that reasoning supports the answer.
- If correct, repeat the candidate answer verbatim.
- If wrong, produce a corrected solution.

OUTPUT STRICTLY:
<reasoning>
... your verification + (if needed) corrected derivation ...
</reasoning>
<answer>... final answer only ...</answer>
"""


# =============================================================================
# Atomic JSON cache helper
# =============================================================================


@dataclass
class Cache:
    root: Path

    def __post_init__(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, stage: str, qid: str) -> Path:
        d = self.root / stage
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{qid}.json"

    def has(self, stage: str, qid: str, allow_failed=False) -> bool:
        p = self.path(stage, qid)
        if not p.exists():
            return False
        if allow_failed:
            return True
        try:
            j = json.loads(p.read_text())
            return bool(j.get("ok"))
        except Exception:
            return False

    def get(self, stage: str, qid: str) -> dict | None:
        p = self.path(stage, qid)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except Exception:
            return None

    def put(self, stage: str, qid: str, payload: dict) -> None:
        p = self.path(stage, qid)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=0))
        tmp.replace(p)


# =============================================================================
# Image helpers
# =============================================================================


def to_data_url(img_field: Any, max_side: int = 1280) -> str | None:
    if img_field is None:
        return None
    raw: bytes | None = None
    fmt = "png"
    if isinstance(img_field, dict):
        raw = img_field.get("bytes")
        path = (img_field.get("path") or "").lower()
        if path.endswith((".jpg", ".jpeg")):
            fmt = "jpeg"
        elif path.endswith(".webp"):
            fmt = "webp"
    elif isinstance(img_field, (bytes, bytearray)):
        raw = bytes(img_field)
    elif isinstance(img_field, Image.Image):
        buf = io.BytesIO()
        img_field.save(buf, format="PNG")
        raw = buf.getvalue()
    if not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw))
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=88)
            raw = buf.getvalue()
            fmt = "jpeg"
    except Exception:
        pass
    return f"data:image/{fmt};base64,{base64.b64encode(raw).decode('ascii')}"


def get_images(row) -> list[Any]:
    f = row.get("images")
    if f is None:
        return []
    try:
        return list(f)
    except TypeError:
        return []


# =============================================================================
# OpenAI-compatible client wrapper with retry
# =============================================================================


def make_client(api_key: str | None, base_url: str | None):
    from openai import OpenAI

    return OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )


def chat(
    client,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    timeout: float,
    max_retries: int = 5,
) -> tuple[str, dict]:
    last_err = None
    for attempt in range(max_retries):
        try:
            r = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )
            text = r.choices[0].message.content or ""
            finish = getattr(r.choices[0], "finish_reason", None)
            usage = {}
            if r.usage:
                usage = {
                    "prompt_tokens": r.usage.prompt_tokens,
                    "completion_tokens": r.usage.completion_tokens,
                    "total_tokens": r.usage.total_tokens,
                }
                # Capture Gemini-specific reasoning_tokens if present
                ctd = getattr(r.usage, "completion_tokens_details", None)
                if ctd is not None:
                    rt = getattr(ctd, "reasoning_tokens", None)
                    if rt is not None:
                        usage["reasoning_tokens"] = rt
            usage["finish_reason"] = finish
            # If the provider truncated for length AND we still have budget, escalate
            if finish == "length" and max_tokens < 131072 and attempt < max_retries - 1:
                sys.stderr.write(
                    f"  [escalate] finish_reason=length; retrying with max_tokens=131072\n"
                )
                max_tokens = 131072
                continue
            return text, usage
        except Exception as e:
            last_err = e
            sleep = min(2 ** attempt, 30) + random.uniform(0, 1.5)
            sys.stderr.write(
                f"  [retry {attempt + 1}/{max_retries}] {type(e).__name__}: {str(e)[:160]}; "
                f"sleeping {sleep:.1f}s\n"
            )
            time.sleep(sleep)
    raise RuntimeError(f"chat failed after {max_retries} retries: {last_err}")


# =============================================================================
# Output parsing
# =============================================================================


def parse_xml(text: str) -> tuple[str, str]:
    reasoning, answer = "", ""
    m = re.search(r"<reasoning>(.*?)</reasoning>", text, re.DOTALL | re.IGNORECASE)
    if m:
        reasoning = m.group(1).strip()
    m = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL | re.IGNORECASE)
    if m:
        answer = m.group(1).strip()
    if not answer:
        m = re.search(r"(?:final\s*answer|answer)\s*[:：]\s*(.+)", text, re.IGNORECASE)
        if m:
            answer = m.group(1).strip().splitlines()[0].strip()
        else:
            cleaned = re.sub(r"</?(?:reasoning|answer)>", "", text, flags=re.IGNORECASE)
            lines = [ln.strip() for ln in cleaned.strip().splitlines() if ln.strip()]
            answer = lines[-1] if lines else ""
    if not reasoning:
        reasoning = text.strip()
    return answer, reasoning


def normalize_answer(ans: str) -> str:
    """Light canonicalization for voting."""
    s = ans.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .。;,")
    # multiple-choice: "A,B,D" / "A B D" / "A、B、D" -> "ABD"
    if re.fullmatch(r"[A-Ea-e][\s,;、和与and]*([A-Ea-e][\s,;、和与and]*)*", s):
        letters = sorted({c.upper() for c in s if c.isalpha()})
        return "".join(letters)
    return s


def majority_vote(answers: list[str]) -> tuple[str, int]:
    if not answers:
        return "", 0
    norm = [normalize_answer(a) for a in answers if a]
    if not norm:
        return answers[0], 0
    c = Counter(norm)
    best, count = c.most_common(1)[0]
    # keep the original spelling of the first sample matching the winning normalized form
    for a in answers:
        if normalize_answer(a) == best:
            return a, count
    return best, count


# =============================================================================
# Stages
# =============================================================================


def stage_caption(client, args, row) -> dict:
    qid = row["question_id"]
    problem = row.get("problem") or ""
    images = get_images(row)
    if not images or not route_use_caption(problem):
        return {"ok": True, "qid": qid, "caption": None, "skipped": True, "reason": "no-image-or-direct-route"}

    # Per-level caption template routing.
    #   L4: "fully visual" — empty problem text, all info in image. Aggressive
    #       verbatim OCR (sub_004, +7q vs default).
    #   L2: hybrid — problem text exists, but in-image values / graph data /
    #       in-image labels are common failure modes. New L23 template forces
    #       explicit extraction of those (sub_007 verification).
    #   Others (L1 N/A no images / L3 / L5): default CAPTION_USER for now.
    qid_str = qid if isinstance(qid, str) else ""
    if qid_str.startswith("level4_"):
        template = L4_CAPTION_USER
        template_tag = "l4"
    elif qid_str.startswith("level2_"):
        template = L23_CAPTION_USER
        template_tag = "l23"
    else:
        template = CAPTION_USER
        template_tag = "default"

    content: list[dict] = [{"type": "text", "text": template.format(problem=problem) if "{problem}" in template else template}]
    for im in images:
        u = to_data_url(im)
        if u:
            content.append({"type": "image_url", "image_url": {"url": u}})

    msg = [{"role": "system", "content": CAPTION_SYSTEM}, {"role": "user", "content": content}]
    text, usage = chat(
        client,
        model=args.caption_model,
        messages=msg,
        max_tokens=args.max_tokens,
        temperature=0.0,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )
    return {
        "ok": True,
        "qid": qid,
        "caption": text.strip(),
        "usage": usage,
        "template": template_tag,
    }


def stage_reason(client, args, row, caption: str | None) -> dict:
    qid = row["question_id"]
    problem = row.get("problem") or ""
    images = get_images(row)

    caption_block = ""
    if caption:
        caption_block = f"\n=== STRUCTURED FIGURE CAPTION ===\n{caption}\n"

    # L1 (text-only) gets the few-shot reason prompt with worked examples.
    # All other levels keep the simpler REASONER_USER (worked examples don't
    # help when the model also needs to attend to a figure).
    qid_str = qid if isinstance(qid, str) else ""
    is_l1 = qid_str.startswith("level1_")
    reason_template = REASONER_USER_L1_FEWSHOT if is_l1 else REASONER_USER

    user_content: list[dict] = [
        {"type": "text", "text": reason_template.format(problem=problem, caption_block=caption_block)}
    ]
    for im in images:
        u = to_data_url(im)
        if u:
            user_content.append({"type": "image_url", "image_url": {"url": u}})

    msg = [{"role": "system", "content": REASONER_SYSTEM}, {"role": "user", "content": user_content}]

    samples = []
    for k in range(args.k_samples):
        temp = 0.0 if k == 0 else args.sc_temperature
        text, usage = chat(
            client,
            model=args.reason_model,
            messages=msg,
            max_tokens=args.max_tokens,
            temperature=temp,
            timeout=args.timeout,
            max_retries=args.max_retries,
        )
        ans, reasoning = parse_xml(text)
        samples.append({"k": k, "temp": temp, "answer": ans, "reasoning": reasoning, "raw": text, "usage": usage})

    answers = [s["answer"] for s in samples]
    voted, votes = majority_vote(answers)
    chosen_idx = next((i for i, s in enumerate(samples) if normalize_answer(s["answer"]) == normalize_answer(voted)), 0)
    chosen = samples[chosen_idx]
    return {
        "ok": True,
        "qid": qid,
        "samples": samples,
        "voted_answer": voted,
        "votes": votes,
        "chosen_idx": chosen_idx,
        "chosen_answer": chosen["answer"],
        "chosen_reasoning": chosen["reasoning"],
    }


def stage_critic(client, args, row, caption: str | None, cand_answer: str, cand_reasoning: str) -> dict:
    qid = row["question_id"]
    problem = row.get("problem") or ""
    images = get_images(row)

    caption_block = f"\n=== STRUCTURED FIGURE CAPTION ===\n{caption}\n" if caption else ""

    user_content: list[dict] = [
        {
            "type": "text",
            "text": CRITIC_USER.format(
                problem=problem,
                caption_block=caption_block,
                cand_answer=cand_answer,
                cand_reasoning=cand_reasoning[:6000],
            ),
        }
    ]
    for im in images:
        u = to_data_url(im)
        if u:
            user_content.append({"type": "image_url", "image_url": {"url": u}})

    msg = [{"role": "system", "content": CRITIC_SYSTEM}, {"role": "user", "content": user_content}]
    text, usage = chat(
        client,
        model=args.critic_model,
        messages=msg,
        max_tokens=args.max_tokens,
        temperature=0.0,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )
    ans, reasoning = parse_xml(text)
    return {"ok": True, "qid": qid, "answer": ans, "reasoning": reasoning, "raw": text, "usage": usage}


# =============================================================================
# Driver
# =============================================================================


def load_split(level: str, split: str) -> pd.DataFrame:
    f = DATA_DIR / level / f"{split}-00000-of-00001.parquet"
    df = pd.read_parquet(f)
    df["__level__"] = level
    df["__split__"] = split
    return df


def process_one(client, args, cache: Cache, row) -> dict:
    qid = row["question_id"]
    # 1) caption
    cap_rec = cache.get("caption", qid)
    if not cap_rec or not cap_rec.get("ok"):
        try:
            cap_rec = stage_caption(client, args, row)
        except Exception as e:
            cap_rec = {"ok": False, "qid": qid, "stage": "caption", "error": str(e)}
            cache.put("caption", qid, cap_rec)
            raise
        cache.put("caption", qid, cap_rec)

    caption = cap_rec.get("caption")

    # 2) reason (k samples + vote)
    rea_rec = cache.get("reason", qid)
    if not rea_rec or not rea_rec.get("ok"):
        try:
            rea_rec = stage_reason(client, args, row, caption)
        except Exception as e:
            rea_rec = {"ok": False, "qid": qid, "stage": "reason", "error": str(e)}
            cache.put("reason", qid, rea_rec)
            raise
        cache.put("reason", qid, rea_rec)

    cand_answer = rea_rec.get("chosen_answer", "")
    cand_reasoning = rea_rec.get("chosen_reasoning", "")

    # 3) critic
    if args.use_critic:
        cri_rec = cache.get("critic", qid)
        if not cri_rec or not cri_rec.get("ok"):
            try:
                cri_rec = stage_critic(client, args, row, caption, cand_answer, cand_reasoning)
            except Exception as e:
                cri_rec = {"ok": False, "qid": qid, "stage": "critic", "error": str(e)}
                cache.put("critic", qid, cri_rec)
                raise
            cache.put("critic", qid, cri_rec)
        final_ans = cri_rec.get("answer") or cand_answer
        final_rea = cri_rec.get("reasoning") or cand_reasoning
    else:
        final_ans, final_rea = cand_answer, cand_reasoning

    final = {
        "ok": True,
        "qid": qid,
        "level": row["__level__"],
        "split": row["__split__"],
        "prediction": final_ans,
        "reasoning": (final_rea or "").strip()[:6000],
        "vote_count": rea_rec.get("votes", 0),
        "k_samples": args.k_samples,
        "had_caption": bool(caption),
    }
    cache.put("final", qid, final)
    return final


def write_csvs(run_dir: Path, cache: Cache):
    rows: list[dict] = []
    final_dir = cache.root / "final"
    if not final_dir.exists():
        print("no final cache; nothing to write")
        return
    for f in final_dir.glob("*.json"):
        try:
            j = json.loads(f.read_text())
        except Exception:
            continue
        if not j.get("ok"):
            continue
        rows.append(j)

    public = [r for r in rows if r.get("split") == "testmini"]
    private = [r for r in rows if r.get("split") == "test"]
    public_csv = run_dir / "prediction.csv"
    private_csv = run_dir / "prediction_private.csv"
    for path, rs in [(public_csv, public), (private_csv, private)]:
        with path.open("w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=["question_id", "prediction", "reasoning"])
            w.writeheader()
            for r in rs:
                w.writerow(
                    {"question_id": r["qid"], "prediction": r.get("prediction", ""), "reasoning": r.get("reasoning", "")}
                )
        print(f"wrote {path} ({len(rs)} rows)")

    import zipfile

    z = run_dir / "submission.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        if public_csv.exists():
            zf.write(public_csv, arcname="prediction.csv")
        if private_csv.exists():
            zf.write(private_csv, arcname="prediction_private.csv")
    print(f"wrote {z}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--run-name", default="v2_default")
    p.add_argument("--split", choices=["testmini", "test", "both"], default="testmini")
    p.add_argument("--levels", nargs="*", choices=ALL_LEVELS, help="default: all")
    p.add_argument("--limit-per-level", type=int, default=0, help="0 = no limit")
    p.add_argument("--limit", type=int, default=0)

    # models
    p.add_argument("--caption-model", default=os.environ.get("CAPTION_MODEL", "gemini-3.1-pro-preview"))
    p.add_argument("--reason-model", default=os.environ.get("REASON_MODEL", "gemini-3.1-pro-preview"))
    p.add_argument("--critic-model", default=os.environ.get("CRITIC_MODEL", "gemini-3.1-pro-preview"))
    p.add_argument("--use-critic", action="store_true", default=True)
    p.add_argument("--no-critic", dest="use_critic", action="store_false")
    p.add_argument("--k-samples", type=int, default=1, help=">1 enables self-consistency voting")
    p.add_argument("--sc-temperature", type=float, default=0.7)

    # api
    p.add_argument("--api-key", default=None)
    p.add_argument("--base-url", default=None)
    p.add_argument("--max-tokens", type=int, default=131072,
                   help="Per-call output budget. Real Gemini-3.1-Pro usage is ~10-15k for hard "
                        "physics; 131072 gives 8-10x safety. Auto-escalates to 131072 if "
                        "finish_reason=length is observed at a smaller budget.")
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--max-retries", type=int, default=5)

    # concurrency
    p.add_argument("--workers", type=int, default=4)

    # control
    p.add_argument("--retry-failed", action="store_true", help="re-attempt rows whose cache says ok=false")
    p.add_argument("--build-csv-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    return p.parse_args()


def main():
    args = parse_args()
    run_dir = OUTPUT_DIR / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    cache = Cache(run_dir / "cache")

    # save config for reproducibility
    cfg_path = run_dir / "config.json"
    cfg = vars(args).copy()
    cfg["api_key"] = "***" if cfg.get("api_key") else None
    cfg_path.write_text(json.dumps(cfg, indent=2))

    if args.build_csv_only:
        write_csvs(run_dir, cache)
        return

    levels = args.levels or ALL_LEVELS
    splits: list[str] = []
    if args.split in ("testmini", "both"):
        splits.append("testmini")
    if args.split in ("test", "both"):
        splits.append("test")

    frames = []
    for lv in levels:
        for sp in splits:
            try:
                d = load_split(lv, sp)
                if args.limit_per_level:
                    d = d.head(args.limit_per_level)
                frames.append(d)
            except FileNotFoundError:
                sys.stderr.write(f"missing: {lv}/{sp} (skip)\n")
    if not frames:
        sys.exit("no data")
    df = pd.concat(frames, ignore_index=True)
    if args.limit:
        df = df.head(args.limit)

    # Filter out already-done rows (based on `final` cache)
    pending: list[dict] = []
    already = 0
    for _, row in df.iterrows():
        qid = row["question_id"]
        if cache.has("final", qid, allow_failed=False) and not args.retry_failed:
            already += 1
            continue
        pending.append(row.to_dict())
    print(f"Total {len(df)} rows; {already} already complete; {len(pending)} pending.")

    if args.dry_run or not pending:
        return

    client = make_client(args.api_key, args.base_url)
    failures_path = run_dir / "failures.jsonl"
    heartbeat_path = run_dir / "heartbeat.json"

    completed = 0
    failed = 0
    t0 = time.time()
    stop = {"flag": False}

    def handle_signal(signum, _frame):
        sys.stderr.write(f"\n[signal {signum}] graceful shutdown requested; finishing in-flight tasks...\n")
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    def runner(row):
        return process_one(client, args, cache, row)

    futures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for row in pending:
            if stop["flag"]:
                break
            futures[ex.submit(runner, row)] = row["question_id"]

        for fut in as_completed(futures):
            qid = futures[fut]
            try:
                fut.result()
                completed += 1
            except Exception as e:
                failed += 1
                err = {
                    "qid": qid,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "error": str(e),
                    "trace": traceback.format_exc()[:2000],
                }
                with failures_path.open("a") as fp:
                    fp.write(json.dumps(err, ensure_ascii=False) + "\n")
                sys.stderr.write(f"FAIL {qid}: {type(e).__name__}: {str(e)[:200]}\n")

            done = completed + failed
            if done % 5 == 0 or done == len(pending):
                dt = time.time() - t0
                rate = done / max(dt, 1e-6)
                eta = (len(pending) - done) / max(rate, 1e-9)
                hb = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "completed": completed,
                    "failed": failed,
                    "pending_total": len(pending),
                    "rate_per_s": round(rate, 3),
                    "eta_minutes": round(eta / 60, 1),
                }
                heartbeat_path.write_text(json.dumps(hb, indent=2))
                print(
                    f"  progress: ok={completed} fail={failed} "
                    f"rate={rate:.2f}/s eta={eta / 60:.1f}m"
                )

    print(f"DONE. ok={completed} fail={failed} elapsed={(time.time() - t0) / 60:.1f}m")
    write_csvs(run_dir, cache)


if __name__ == "__main__":
    main()
