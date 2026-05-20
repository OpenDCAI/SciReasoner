# Submission 8 — L1 few-shot worked examples (Gemini-3.1-Pro) ✓✓ NEW BEST

- **Submitted**: 2026-05-20 ~15:20
- **Overall score**: **0.7771** (645/830 correct, **+2 questions vs sub_004**) ← NEW BEST
- **Per level**: L1 **0.770**, L2 0.800, L3 0.765, L4 0.750, L5 0.933

## Per-level deltas vs sub_004

| Level | sub_004 | sub_008 | Δq | Real signal? |
|---|---:|---:|---:|---|
| **L1** | **0.765** | **0.770** | **+1** | **marginal** — at the noise floor; 13 real-disagreement coin flips landed slightly better than random |
| L2 | 0.810 | 0.800 | −2 | NO — judge noise (L2 cache untouched) |
| L3 | 0.760 | 0.765 | +1 | NO — judge noise (L3 cache untouched) |
| L4 | 0.740 | 0.750 | +2 | NO — judge noise (L4 cache untouched) |
| L5 | 0.933 | 0.933 | 0 | unchanged |

**Net +2 questions overall** = ~0.24pp = NEW BEST 0.7771. The non-L1 deltas
sum to +1 (pure level-by-level judge nondeterminism, ±2 range as documented).
The L1 +1q is at the noise floor (cerebrum says ±1-2 swings happen on
untouched levels) but unlike sub_005/006 it's positive, not negative.

## Pipeline change vs sub_004

Only **L1** was re-run with a new reason prompt. New `REASONER_USER_L1_FEWSHOT`
prepends 3 worked physics examples (mechanics+friction, RC discharge, multichoice
energy diagram) to the existing reason instructions. Each example shows the
full `<reasoning>...</reasoning><answer>...</answer>` block.

L1 caption stage skipped (text-only). 199 questions ran the new prompt;
1 question (`level1_testmini_000174`) hit truncation in BOTH reason and critic
(model went into a loop trying to interpret the rotating-disk problem) → restored
from sub_004 baseline as fallback.

L2 / L3 / L4 / L5 caches untouched (sub_004 baseline).

## Mid-run interruption

Gemini key ran out of quota at sub_007 + sub_008 boundary. After top-up, the
pipeline resumed cleanly (cache atomic-write means no double-billing). 0 total
failures after resume.

Wall time: 8.2 min initial run + 15.4 min resume = 23.6 min for 200 L1 questions.

## Diff vs sub_004

- Non-L1 levels: identical (cache untouched)
- **L1: 51/200 answers changed (25.5%)** — almost twice the SC k=3 churn (24/200)
- 1 fallback restoration (`level1_testmini_000174` reverted to sub_004 baseline)

### Categorization of the 51 L1 changes

**Format mimicry of worked examples (~38 of 51 = 75%)** ← model copied the
LaTeX formatting style from the few-shot examples:
- `1 m/s` → `1\,\mathrm{m/s}` (added `\mathrm` wrap and `\,` thin space)
- `2L/5` → `\frac{2}{5}L`
- `\sqrt{8/35}` → `\sqrt{\frac{8}{35}}`
- `7\sqrt{95}/475` → `\frac{7\sqrt{95}}{475}`
- `300` → `300\,\mathrm{N}` (model added units to bare numerics, mimicking
  example 1's `\sqrt{35}\,\mathrm{m/s}`)
- `1.75` → `1.75\,\mathrm{cm}` (units added)
- `1/15` → `1/15\,\mathrm{m}` (units added)
- 30+ similar `\,\mathrm{...}` wraps and `\frac` rewrites

These are exactly the format-equivalent rewrites that **sub_005 already proved
neutral** for the deepseek-v4-pro semantic judge (40 rewrites, 0 score impact).

**Real semantic disagreements (~13 of 51, ~50/50)**:
| qid | sub_004 | sub_008 | Note |
|---|---|---|---|
| `000007` | `\frac{4mv_0R}{B²d²}` | `-\frac{4mv_0R}{B²d²}` | **sign flip** — one is wrong |
| `000118` | `0.012 C` | `0.024 C` | factor-of-2 difference |
| `000069` | `\sqrt{0.6321}` | `0.8` | precision rounding (≈0.795 → 0.8) |
| `000079` | `14.22` | `14.2` | precision |
| `000098` | `0 ≤ μ ≤ 28/75` | `28/75 ≤ μ < 0.5` | range flip (also seen in sub_006) |
| `000117` | `2.5×10⁻⁹ C/m²` | `\frac{490√3}{3}ε₀ C/m²` | symbolic vs numerical |
| `000129` | `π/5, 2π/5, 3π/5 rad/s` | `π/5 rad/s` | dropped 2 frequencies (also sub_006) |
| `000156` | `x = ...` | `x(t) = ...` | added explicit variable |
| `000095` | factored form | reorganized | factored equiv |
| `000115` | factor reorder | factor reorder | equivalent |
| `000178` | bracket size | bracket size | cosmetic |
| `000148` | `(1-\frac{\sqrt{2}}{4})g` | `\left(...\right)g` | bracket sizing |
| `000168` | `10\sqrt{3}/3` | `\frac{10\sqrt{3}}{3}` | frac form |

The most likely real losses are `000129` (dropped frequencies, also lost in
sub_006) and possibly `000007` (sign flip). The 13 disagreements split ~5-7
either way → expected net −1 to +1 on real signal, plus 38 format-equivalent
that net 0.

## Why the few-shot didn't unlock new physics

The deepseek judge is form-tolerant (cerebrum DNR). Few-shot examples that show
both physics derivation AND parseable LaTeX format are easier for the model to
imitate at the *format* level than at the *reasoning* level. So the model
absorbed the formatting (`\,\mathrm{...}`, `\frac` wrappers) but didn't
restructure its physics derivations.

This is the third confirmation of: **prompt-level interventions on Gemini-3.1-Pro
do not unlock new accuracy on this benchmark**. The pipeline accuracy is
bounded by what the underlying model can do given problem text + structured
caption.

## Audit fixes applied (3)

3 L5 lowercase → uppercase (carry-over).
1 truncation case (`level1_testmini_000174`) restored from sub_004 baseline before
audit (in cache, not as audit step).

## Cost

~$280 actual (200 L1 questions × $1.40 avg, including the 30% wasted on the
key-quota interrupt + retry overhead). Cumulative experiment spend ~$3000.

## Files

- `submission.zip` — built from prediction_audited.csv (= renamed inside zip)
- `prediction.csv` = `prediction_audited.csv`
- `prediction_pre_audit.csv` — raw output before audit
- `prediction_private.csv` — empty
- `audit_report.md`
- `prediction_result.zip` / `scoring_result.zip` — pending Codabench scoring

## Going forward

Three independent attempts (sub_005 v3 prompt, sub_006 SC k=3, sub_008 few-shot)
have now confirmed the same finding: **pipeline accuracy on L1 is bounded by
the underlying model, not by prompt engineering**. To go further on L1:

1. **Different reason model entirely** — but cerebrum DNR forbids this
   (heterogeneous model swap proven to lose 53q in sub_002).
2. **Concede L1 = 0.765** as the model's ceiling on this judge.
3. **Run private leaderboard** with sub_004 config (mandatory for prize).

## Lesson (CONFIRMED post-upload)

L1 few-shot with worked examples gave **net +1q on L1** (and +2q overall once
judge noise on untouched levels is included). This is at the noise floor — we
cannot rule out it being random level-by-level variation. But the sign is
**different from sub_005 (v3 prompt: 0)** and **sub_006 (SC k=3: −1)**, both of
which had similar churn rates.

Tentative cerebrum update: format mimicry with parseable LaTeX wraps
(`\,\mathrm{...}`, explicit `\frac{...}` etc.) might help **slightly** on the
deepseek judge — possibly because it reaches deterministic-match more often
(local_correct 612 → 613). But the effect is small enough (≤1q) that we
shouldn't bet a budget on replicating it.

**The score 0.7771 is real and submitted.** That's what matters.
