# Submission 4 — L4-specific aggressive caption template ✓✓ BIG WIN

- **Submitted**: 2026-05-19 ~21:30
- **Overall score**: **0.7747**   (= 643/830 correct, **+7 questions vs sub_003**)
- **Per level**: L1 0.765, L2 0.810, L3 0.760, L4 **0.740**, L5 0.933

## Per-level deltas vs sub_003

| Level | sub_003 | sub_004 | Δ questions | Real signal? |
|---|---:|---:|---:|---|
| L1 | 0.770 | 0.765 | −1 | NO — judge noise (didn't touch L1) |
| L2 | 0.800 | 0.810 | +2 | NO — judge noise (didn't touch L2) |
| L3 | 0.765 | 0.760 | −1 | NO — judge noise (didn't touch L3) |
| **L4** | **0.705** | **0.740** | **+7** | **YES — far above ±2-q noise floor** |
| L5 | 0.933 | 0.933 | 0 | unchanged |

The L4 caption upgrade alone delivered +7 questions on L4 (200 questions),
which is the entire +7 question gain on overall. This is the first
confirmed real-signal improvement we've found.

## Pipeline change vs Sub 3 (current 0.7663 baseline)

Only L4 was re-run. L1/L2/L3/L5 cache untouched, so their answers are identical to sub_003.

For all 200 L4 questions, the caption stage uses a **new template** triggered by
`qid.startswith("level4_")`:

```
[QUESTION STEM (verbatim)]:    ← NEW: full transcription of in-image question text
[GIVEN VALUES]:                ← NEW: explicit list of every value+unit
[FIGURE TYPE]:
[OBJECTS / BODIES]:
[FORCES / VECTORS]:
[FIELDS / REGIONS]:
[GEOMETRY]:
[GRAPHS / PLOTS]:              ← NEW: axes, ticks, curves, equations
[OPTIONS (verbatim)]:          ← NEW: A/B/C/D options as printed
[SUB-QUESTIONS]:               ← NEW
[CONSTRAINTS / REFERENCE STATES]:
[NOTES]:
```

L1/L2/L3/L5 still use the original CAPTION_USER template.

## Why
L4 has empty `problem` field — all info is in the image. The original "structured
caption" template was designed for problems where text gives context and the image
has extra detail; L4 inverts this. Forcing verbatim OCR of question stem + options
+ values gives the reasoner solid ground.

## Subsample (30 questions, dropped on first L4 caption run)
- Caption mean tokens: 3580 → 6528 (+82%)
- Caption mean chars: 1415 → 2272 (+60%)
- 5/30 answers changed (16.7%)
- Notable: level4_testmini_000027 went from leaked-reasoning fallback to clean "BD"

## Full 200-question delta vs sub_003
- L4 caption mean chars: 1491 → 2363 (1.58x growth)
- L4 answers changed: 50/200 (25%)
- L4 truncation cases (3 in sub_003): all now resolved with clean answers, no audit fallback needed

## Audit on this run
Only 3 fixes (the 3 L5 lowercase multichoice). The 3 critic-truncation fallbacks
that drove sub_003's +1pp on L4 are no longer needed because the new L4 caption
prevents the truncation in the first place.

## Files
- `submission.zip` — what to upload (= prediction_audited.csv as prediction.csv inside)
- `prediction.csv` — same content as the audited CSV
- `prediction_audited.csv` — after 3 audit fixes
- `prediction_pre_audit.csv` — raw output before audit
- `prediction_private.csv` — empty (haven't run private split yet)
- `prediction_result.zip` — Codabench echo
- `scoring_result.zip` — Codabench's scores.json + diagnostics.json

## Scoring diagnostics
- judge: deepseek/deepseek-v4-pro (semantic, answer-only mode)
- 706/830 deterministically scored (612 correct), 124 sent to LLM judge
- 0 invalid, 0 missing
- local_correct: 612 (up from 599 in sub_003 = +13 deterministic)
- items_to_llm: 124 (down from 130 = fewer borderline)
- Both deltas are consistent with: better-formatted L4 answers reach the deterministic match path more often.

## Lesson
Targeted, level-specific caption template **works** when there's a clear input/output
mismatch. L4 has zero text — the original template treated text as primary and image
as supplementary. Inverting that (verbatim image OCR upfront) added structure the
solver could rely on, recovering ~3.5% of L4 questions.
