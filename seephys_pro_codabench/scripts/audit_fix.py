#!/usr/bin/env python3
"""
Audit + post-process the 830 predictions of v2_pub830 to fix format issues.

Fixes applied (deterministic, $0):
  A. critic finish_reason=length → fallback to reason's chosen_answer (if reason finished cleanly)
  B. all-lowercase multi-choice (e.g. 'bd') → uppercase ('BD')
  C. strip trailing whitespace, period, surrounding markdown, etc.
  D. drop residual <answer>/<reasoning> tags
  E. unwrap \\boxed{...} when the entire answer is wrapped

Outputs:
  output/v2_pub830/prediction_audited.csv
  output/v2_pub830/submission_audited.zip
  output/v2_pub830/audit_report.md  (human-readable summary)
  output/v2_pub830/needs_rerun.json  (list of qids whose reason ALSO truncated; both stages bad)
"""

from __future__ import annotations
import csv, json, re, zipfile
from pathlib import Path

RUN = Path("/Users/lianghao/Desktop/SeePhy/output/v2_pub830")
CACHE = RUN / "cache"

PRED_IN = RUN / "prediction.csv"
PRED_OUT = RUN / "prediction_audited.csv"
ZIP_OUT = RUN / "submission_audited.zip"
REPORT = RUN / "audit_report.md"
NEED_RERUN = RUN / "needs_rerun.json"


def load_cache(stage: str, qid: str) -> dict | None:
    p = CACHE / stage / f"{qid}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def is_clean_answer(text: str) -> bool:
    """A clean answer has no leaked reasoning, no incomplete LaTeX, decent length."""
    if not text:
        return False
    t = text.strip()
    if len(t) > 500:
        return False
    # Leaked reasoning markers
    if re.search(
        r"\b(let'?s|usually,? if|otherwise|maybe|perhaps|i think|let me|"
        r"checking|now,? let|considering)\b",
        t, re.I,
    ):
        return False
    # Truncated mid-formula (open math env or trailing operator)
    open_braces = t.count("{") - t.count("}")
    if open_braces > 1:
        return False
    if re.search(r"[\\\$=+\-/*,]\s*$", t):
        return False
    return True


def normalize(ans: str) -> str:
    s = ans or ""
    # Strip residual XML tags
    s = re.sub(r"</?(reasoning|answer)>", "", s, flags=re.I)
    # Strip leading "Answer:", "Final Answer:", etc.
    s = re.sub(r"^\s*(?:final\s+answer|answer|so|therefore)\s*[:：]\s*", "", s, flags=re.I)
    # Unwrap \boxed{...} if entire answer is wrapped
    m = re.fullmatch(r"\s*\\boxed\{(.+)\}\s*", s, re.S)
    if m:
        s = m.group(1)
    # Strip surrounding markdown emphasis
    s = re.sub(r"^[*_`\s]+|[*_`\s]+$", "", s)
    # Strip trailing single period (but keep within decimals like "3.14")
    s = re.sub(r"(?<![0-9])\.\s*$", "", s)
    s = s.strip()
    # Multi-choice lowercase → uppercase (only when entire answer is lowercase a-e letters)
    if re.fullmatch(r"[a-e]+", s):
        s = s.upper()
    # Multi-choice with separators → squashed uppercase letters in alphabetical order
    if re.fullmatch(r"[A-Ea-e](?:[\s,，;；、和与andAND]+[A-Ea-e])+\.?", s):
        letters = sorted({c.upper() for c in s if c.isalpha()})
        if letters and all(c in "ABCDE" for c in letters):
            s = "".join(letters)
    return s.strip()


def main():
    rows_in = list(csv.DictReader(open(PRED_IN)))
    print(f"Loaded {len(rows_in)} rows from {PRED_IN}")

    fixes_applied = {
        "critic_fallback_to_reason": [],
        "uppercase_multichoice": [],
        "boxed_unwrap": [],
        "tag_strip": [],
        "leading_label_strip": [],
        "trailing_period_strip": [],
        "punct_multichoice_squash": [],
    }
    needs_rerun = []  # both stages truncated/bad

    rows_out = []
    for r in rows_in:
        qid = r["question_id"]
        original = r.get("prediction", "") or ""
        new_pred = original
        new_reasoning = r.get("reasoning", "")

        # Fix A: critic truncation fallback
        critic = load_cache("critic", qid)
        if critic and isinstance(critic.get("usage"), dict):
            fin = critic["usage"].get("finish_reason")
            critic_ans = (critic.get("answer") or "").strip()
            if fin == "length" or not is_clean_answer(critic_ans):
                # Try reason fallback
                reason = load_cache("reason", qid)
                ok_sample = None
                if reason:
                    for s in reason.get("samples", []):
                        u = s.get("usage") or {}
                        sf = u.get("finish_reason") if isinstance(u, dict) else None
                        cand = (s.get("answer") or "").strip()
                        if sf == "stop" and is_clean_answer(cand):
                            ok_sample = s
                            break
                if ok_sample:
                    new_pred = ok_sample["answer"]
                    new_reasoning = (ok_sample.get("reasoning") or "")[:6000]
                    fixes_applied["critic_fallback_to_reason"].append(
                        {"qid": qid, "from": original[:80], "to": new_pred[:80]}
                    )
                else:
                    needs_rerun.append({
                        "qid": qid,
                        "level": qid.split("_")[0] if not qid.startswith("solve") else "level5",
                        "critic_finish": fin,
                        "critic_answer_head": critic_ans[:80],
                    })

        # Fix B/C/D/E: format normalization
        before = new_pred
        normalized = normalize(new_pred)
        if normalized != before:
            if re.fullmatch(r"[A-E]+", normalized) and re.fullmatch(r"[a-e]+", before.strip()):
                fixes_applied["uppercase_multichoice"].append({"qid": qid, "from": before, "to": normalized})
            elif re.search(r"\\boxed\{", before):
                fixes_applied["boxed_unwrap"].append({"qid": qid, "from": before[:80], "to": normalized[:80]})
            elif re.search(r"</?(reasoning|answer)>", before, re.I):
                fixes_applied["tag_strip"].append({"qid": qid})
            elif re.match(r"^\s*(answer|final answer)\s*[:：]", before, re.I):
                fixes_applied["leading_label_strip"].append({"qid": qid})
            elif before.endswith("."):
                fixes_applied["trailing_period_strip"].append({"qid": qid})
            elif "," in before or "、" in before:
                fixes_applied["punct_multichoice_squash"].append({"qid": qid, "from": before, "to": normalized})
            else:
                fixes_applied.setdefault("other_normalize", []).append({"qid": qid, "from": before[:80], "to": normalized[:80]})
            new_pred = normalized

        rows_out.append({
            "question_id": qid,
            "prediction": new_pred,
            "reasoning": new_reasoning,
        })

    # Write output CSV
    with open(PRED_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["question_id", "prediction", "reasoning"])
        w.writeheader()
        for r in rows_out:
            w.writerow(r)
    print(f"Wrote {PRED_OUT}")

    # Build submission.zip
    private_csv = RUN / "prediction_private.csv"
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(PRED_OUT, arcname="prediction.csv")
        if private_csv.exists():
            z.write(private_csv, arcname="prediction_private.csv")
    print(f"Wrote {ZIP_OUT}")

    # Write report
    lines = ["# Audit Report — v2_pub830", ""]
    total_fixes = sum(len(v) for v in fixes_applied.values())
    lines.append(f"Total fixes applied: **{total_fixes}**")
    lines.append(f"Questions needing re-run (both critic & reason truncated/bad): **{len(needs_rerun)}**")
    lines.append("")
    for k, v in fixes_applied.items():
        if not v:
            continue
        lines.append(f"## {k} ({len(v)})")
        for item in v[:10]:
            lines.append(f"- `{item.get('qid')}`: `{item.get('from','')!r}` → `{item.get('to','')!r}`")
        if len(v) > 10:
            lines.append(f"- ... and {len(v)-10} more")
        lines.append("")
    if needs_rerun:
        lines.append("## needs_rerun")
        for item in needs_rerun:
            lines.append(f"- `{item['qid']}` ({item['level']}): critic_finish={item['critic_finish']}, "
                         f"head=`{item['critic_answer_head']!r}`")
    REPORT.write_text("\n".join(lines))
    print(f"Wrote {REPORT}")

    NEED_RERUN.write_text(json.dumps(needs_rerun, indent=2))
    print(f"Wrote {NEED_RERUN}")
    print()
    print(f"--- summary ---")
    print(f"  fixes:           {total_fixes}")
    print(f"  needs_rerun:     {len(needs_rerun)}")
    for k, v in fixes_applied.items():
        if v:
            print(f"  {k}: {len(v)}")


if __name__ == "__main__":
    main()
