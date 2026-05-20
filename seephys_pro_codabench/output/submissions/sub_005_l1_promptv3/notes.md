# Submission 5 — L1 reason+critic with refined prompt v3 (Gemini-3.1-Pro)

- **Submitted**: 2026-05-19 ~23:09
- **Overall score**: **0.7735**   (= 642/830 correct, **−1 question vs sub_004**)
- **Per level**: L1 0.765, L2 0.800, L3 0.760, L4 0.745, L5 0.933

## Per-level deltas vs sub_004

| Level | sub_004 | sub_005 | Δ q | Real signal? |
|---|---:|---:|---:|---|
| L1 | 0.765 | 0.765 | 0 | **L1 unchanged despite 40 answer rewrites** — biggest finding |
| L2 | 0.810 | 0.800 | −2 | NO — judge noise (didn't touch L2) |
| L3 | 0.760 | 0.760 | 0 | NO change |
| L4 | 0.740 | 0.745 | +1 | NO — judge noise (didn't touch L4) |
| L5 | 0.933 | 0.933 | 0 | unchanged |

## Diagnostics

| | sub_004 | sub_005 | Δ |
|---|---:|---:|---|
| local_correct | 599 | 617 | +18 (more exact matches) |
| items_to_llm | 130 | 120 | −10 (less LLM-dependent) |
| local_scored | 706 | 710 | +4 |

The new prompt produced more deterministically-matchable answers. But the LLM judge
already handled the older messier answers about as well — net effect on accuracy: zero.

## Two iterations of the prompt

- **v2 (rejected)**: too aggressive on unit stripping. "10 V" → "10", "95 kΩ" → "95000".
  gpt-5.4 juror referee predicted −5 questions. Stashed in `cache_l1_promptv2_NOT_USED`.
- **v3 (this submission)**: keeps natural units; predicted −2 by referee.
  Actual: L1 unchanged (0 net), Overall −1 due to L2 judge noise.

## Big lesson: format rules have LOW ROI on this benchmark

The deepseek-v4-pro semantic judge is **tolerant of equivalent forms**:
- `\sqrt{8/35}` and `\frac{2\sqrt{70}}{35}` both judged correct
- `m_A ≥ 2.4` and `m_A ≥ 2.4 kg` both judged correct
- `2L/5` and `\frac{2}{5}L` both judged correct

Tightening the prompt reduces LLM-judge dependency (good for reproducibility) but
doesn't change which questions are right/wrong. The 47/200 wrong L1 questions are
**real reasoning errors**, not format issues.

## Cost of this iteration
- v2 prompt run: ~$160 (rejected, not submitted)
- v3 prompt run: ~$160 (submitted as sub_005)
- Total: ~$320 — confirmed format prompting has near-zero ROI

## Going forward for L1 (reasoning, not format)

The path to closing the L1 gap (currently 0.765 vs ctree's 0.79) is:
1. **SC k=3 with Gemini** — let Gemini retry unstable reasoning paths, vote
2. **Few-shot worked physics examples** — guide reasoning, not formatting
3. **Domain-routed prompts** — different setups for mech / EM / thermo / optics

## Files
- `submission.zip` — what was uploaded
- `prediction.csv` / `prediction_audited.csv` — same content
- `prediction_pre_audit.csv` — raw v3 output
- `prediction_private.csv` — empty
- `prediction_result.zip` — Codabench echo
- `scoring_result.zip` — Codabench scores.json + diagnostics
