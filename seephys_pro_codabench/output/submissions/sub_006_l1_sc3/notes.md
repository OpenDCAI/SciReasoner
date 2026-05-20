# Submission 6 — L1 Self-Consistency k=3 (Gemini-3.1-Pro, T=0.7)

- **Submitted**: 2026-05-20 ~13:10
- **Overall score**: **0.7735** (642/830 correct, **−1 question vs sub_004**)
- **Per level**: L1 **0.760**, L2 0.805, L3 0.760, L4 0.745, L5 0.933

## Per-level deltas vs sub_004

| Level | sub_004 | sub_006 | Δq | Real signal? |
|---|---:|---:|---:|---|
| **L1** | **0.765** | **0.760** | **−1** | **YES — L1 was the only level re-run** |
| L2 | 0.810 | 0.805 | −1 | NO — judge noise (didn't touch L2) |
| L3 | 0.760 | 0.760 | 0 | unchanged |
| L4 | 0.740 | 0.745 | +1 | NO — judge noise (didn't touch L4) |
| L5 | 0.933 | 0.933 | 0 | unchanged |

**Headline**: same-model SC k=3 at T=0.7 cost $160 to lose 1 L1 question.
gpt-5.4 referee predicted exactly this (net −1q, mostly from `level1_testmini_000156`
where SC voted to stop at the ODE without solving it).

## Diagnostics

| | sub_004 | sub_006 | Δ |
|---|---:|---:|---|
| local_correct | 612 | 615 | +3 (more deterministic matches) |
| items_to_llm | 124 | 121 | −3 (slightly less LLM-dependent) |
| local_scored | 706 | 709 | +3 |

Same pattern as sub_005: cleaner formatted answers reach the deterministic
match path more often, but **the LLM judge already handled the messier ones
about as well — net effect is a slight loss**.

## Pipeline change vs sub_004 (current best 0.7747)

Only L1 was re-run. **Same v1 reason prompt** as sub_003/sub_004 (sub_005's v3
prompt was rolled back per cerebrum DNR — format rules have ~0 ROI). On top of
v1 prompt, run **Self-Consistency k=3** with temperature 0.7 on the
`stage_reason` step:

```
caption (cached)  →  reason × 3 samples (T=0.7)  →  majority_vote()  →  critic (re-run on voted reason)
```

Caption / critic models unchanged (Gemini-3.1-Pro). 50 concurrent workers. Total
wall time 38.2 min, 0 failures.

## SC vote distribution (200 L1 questions)

| Pattern | Count | Note |
|---|---:|---|
| 3-0 unanimous | 151 (75.5%) | Reasoner is stable — SC was a no-op |
| 2-1 split | 38 (19.0%) | Majority breaks tie |
| 1-1-1 three-way | 11 (5.5%) | Falls back to first sample |

**75% of L1 is already deterministic** at T=0.7. SC only matters on the 49
non-unanimous cases; of those, 23 of 24 final-answer changes vs sub_004 came
from non-unanimous votes (SC's intended use case).

## Diff vs sub_004 submitted answers

- **Non-L1 levels**: identical (cache untouched). Confirmed via zipped
  prediction.csv comparison.
- **L1**: 24/200 answers changed (12%).
- **L1 reasoning text**: 176/200 differ (because SC picks one of three samples
  to attach as the `reasoning` column; this is purely cosmetic since the judge
  cares about answer + reasoning support, not exact wording).

### Categorization of the 24 L1 answer changes

**Cosmetic / equivalent forms** (~17 of 24, judge accepts both):
- `\frac{4mv_0R}{B^2d^2}` ↔ `\frac{4mRv_0}{B^2d^2}` (factor reorder)
- `\frac{2\sqrt{3}}{27}\frac{v_0^2}{R^2}` ↔ `\frac{2\sqrt{3}v_0^2}{27R^2}`
- `-\frac{1}{17}\omega_0` ↔ `-\omega_0/17`
- `0.1` ↔ `0.10` (precision)
- `W/\sqrt{3}` ↔ `\frac{\sqrt{3}}{3}W` (rationalized)
- `\arccos(37/40)` ↔ `\arccos(0.925)` (37/40 = 0.925)
- `\frac{\pi}{4}\sqrt{\frac{2l}{g}}` ↔ `\frac{\pi}{2}\sqrt{\frac{l}{2g}}`
  (both = π/(2√2)·√(l/g))
- `\frac{\pi}{2}\sqrt{\frac{5g}{R}}` ↔ `\frac{\sqrt{5}\pi}{2}\sqrt{\frac{g}{R}}`
- `\sqrt{\frac{35mg+6kl}{24ml}}` ↔ `\sqrt{\frac{175}{12l}+\frac{k}{4m}}`
  (g=10 substituted)
- `\epsilon_0` ↔ `\varepsilon_0` (same symbol)
- bracket / spacing tweaks
- `\sqrt{65/56}` → `\sqrt{65/56} m/s` (added natural unit)

**Real semantic disagreements** (~7 of 24, one form is wrong):
| qid | sub_004 | sub_006 | gpt-5.4 referee call |
|---|---|---|---|
| `000079` | `14.22` | `14.16` | sub_006 likely correct (cleaner derivation) |
| `000098` | `0 ≤ μ ≤ 28/75` | `28/75 ≤ μ < 0.5` | unclear — opposite ranges |
| `000117` | `2.5×10⁻⁹ C/m²` | `\frac{490√3}{3}ε₀` | likely equivalent |
| `000129` | `π/5, 2π/5, 3π/5 rad/s` | `π/5 rad/s` | sub_004 likely better (3 frequencies asked) |
| `000156` | explicit `x(t)=...` | ODE only | **sub_006 worse** (incomplete) |
| `000184` | `BD` | `D` | unclear (multichoice, one option lost) |
| `000198` | `52/3` | `34` | unclear (52/3≈17.3 ≠ 34) |

**gpt-5.4 referee verdict** (predictive only, before judge):
- 0 wins for sub_006
- 1 likely-loss (`000156` — sub_006 stops at the ODE without solving)
- 6 toss-ups within judge tolerance
- **Net: −1 question on L1**

## Audit fixes applied (4)

1 critic_fallback_to_reason (`level1_testmini_000106` — critic truncated mid-token)
3 L5 lowercase → uppercase (`solve150_*_000011/000012/000014`, all 3 are leftover
from sub_004 baseline; reapplied as audit step is idempotent.)

## Why SC k=3 may not move the needle

1. **75% of L1 is unanimous** — the model is already stable on most questions
2. The 25 non-unanimous cases overlap heavily with **format-equivalent** answers,
   not reasoning errors
3. The remaining ~7 reasoning disagreements split roughly 50-50 — no systematic
   accuracy gain
4. sub_005 already proved the deepseek judge is **form-tolerant**, so cosmetic
   tweaks ↔ 0 score impact

This is consistent with cerebrum DNR: "format rules have low ROI; must attack
reasoning quality directly." SC k=3 is a *small* attack on reasoning quality
(reduces variance) but the variance was already low at T=0.7.

## Cost

~$160 (3× reason calls at Gemini-3.1-Pro for 200 L1 questions, plus 1 critic
re-run). Cumulative experiment spend now ~$2300.

## Files

- `submission.zip` — built from prediction_audited.csv (= renamed inside zip)
- `prediction.csv` = `prediction_audited.csv`
- `prediction_pre_audit.csv` — raw SC k=3 + voted output before audit
- `prediction_private.csv` — empty
- `audit_report.md` — copy of the audit report
- `prediction_result.zip` / `scoring_result.zip` — pending Codabench scoring

## Going forward

If sub_006 confirms ≈ −1 to +1 (within noise), this puts a hard cap on:
1. **Pure SC at low temperature** — model is too deterministic to benefit
2. **Format-only changes** — judge doesn't care

Then real path forward is:
1. **Few-shot worked physics examples** in the reason prompt (target reasoning,
   not formatting)
2. **L2 / L3 verbatim caption template** (mirroring sub_004's L4 win — those
   levels also have heavy in-image content)
3. **High-temperature SC k=5 with chain-of-thought diversification** (force
   different solution paths, vote)
4. **Domain-routed prompts** for L1 (mech / EM / thermo / optics each get a
   tailored system prompt)

## Lesson (CONFIRMED post-upload)

Same-model SC k=3 at T=0.7 on a model that already converges 75% of the time =
expensive net loss. To get value from SC, either crank T (more diversity) or k
(more samples), or both — but cost scales linearly. Better lever for L1 is
likely *prompt content* (worked examples, domain routing), not *sampling*.

**gpt-5.4 referee was accurate** (predicted −1, observed −1). Going forward,
referee can be used as a pre-upload filter for low-impact L1 changes to avoid
wasting daily quota.
