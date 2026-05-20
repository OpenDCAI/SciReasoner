# Submission 7 — L2 verbatim caption template (Gemini-3.1-Pro)

- **Submitted**: pending (held for upload decision)
- **Predicted overall**: 0.7735–0.7758 (net −1 to +2 vs sub_004's 0.7747)
- **Per level (predicted)**: L1 0.765, L2 ~0.805–0.815, L3 0.760, L4 0.740, L5 0.933

## Pipeline change vs sub_004 (current best 0.7747)

Only **L2** was re-run with a new caption template. New `L23_CAPTION_USER` is a
hybrid of default + L4 verbatim style:

```
[FIGURE TYPE]
[OBJECTS / BODIES]
[FORCES / VECTORS]
[FIELDS / REGIONS]
[GEOMETRY]
[GIVEN VALUES IN IMAGE]:           ← NEW (forced exhaustive in-image numerics)
[GRAPHS / PLOTS]:                  ← strengthened (axes, ticks, key points)
[OPTIONS / LABELS IN IMAGE]:       ← NEW (only when present in figure)
[IN-IMAGE TEXT / ANNOTATIONS]
[CONSTRAINTS / REFERENCE STATES]
[NOTES]
```

L1 stayed v1 prompt (restored from `cache_backup_pre_l1_sc3`).
L3 / L4 / L5 caches untouched. Only the 138 L2 questions that already had captions
were invalidated (62 L2 text-only questions that `route_use_caption` skips were
left as-is).

## Caption growth on L2 (138 questions)

|  | sub_004 | sub_007 | Δ |
|---|---:|---:|---|
| Mean chars | 1272 | 1714 | +35% |
| Mean completion tokens | 2434 | 2523 | +4% |

For comparison, L4 went +58% / +5% on chars/tokens. L2 grows less because the
problem text already gives most of the structure; the new template mainly adds
the [GIVEN VALUES IN IMAGE] section.

## Diff vs sub_004

- Non-L2 levels: identical (L1/L3/L4/L5 cache untouched)
- **L2: 23/200 answers changed (11.5%)**

Wall time: 17 min for 138 questions (50 concurrent workers, 0 failures).

### Categorization of the 23 L2 answer changes

**Format-equivalent (~13 of 23, judge accepts both — confirmed by sub_005)**:
- `\frac{2L}{5}` ↔ `\frac{2}{5}L`
- `\sqrt{8/35}` ↔ `\frac{2\sqrt{70}}{35}` (rationalized)
- `15/\sqrt{7} - 64/(3\sqrt{41})` ↔ `\frac{15\sqrt{7}}{7}-\frac{64\sqrt{41}}{123}`
- `-11/65\omega_0` ↔ `-\frac{11}{65}\omega_0`
- whitespace / `\frac` ↔ `/` / unit-formatting tweaks
- `R \ge 9.0` ↔ `R \ge 9`
- `3mg - 2mg\cos\theta + ...` ↔ `mg(3 - 2\cos\theta) + ...` (factored equiv)

**Real semantic disagreements (~9 of 23, ~50/50 outcome)**:
| qid | sub_004 | sub_007 | Note |
|---|---|---|---|
| `000048` | `4.12 × 10^4 s` | complex √ expression | one is wrong; sub_007 keeps symbolic |
| `000061` | `√3 L/4` | `L/4` | different geometry |
| `000084` | `2` | `(4-√15)/6 ≈ 0.024` | very different |
| `000115` | `(487π/180+3/5)R/v₀` | `R/v₀(5π/2+3/5+arcsin(3/5))` | different evaluation |
| `000127` | `12+10√2 N` | `12+10√2` | unit dropped (could lose) |
| `000136` | scalar `2mA²ω²sinθcosθ` | vector form | different physical claim |
| `000182` | `D` | `B` | multichoice swap |
| `000189` | `15` | `-5` | different number |
| `000196` | `√(60R₁)` | `√(40R₁+10R₂)` | different formula |

**Confirmed regression (1/23)** ← cerebrum DNR violation:
- `000193`: `L - L_A - h` → **`Cannot be determined`**
  - "Cannot be determined uniquely" was the **gpt-5.5 sub_002 hedging failure
    mode** that lost 53 questions. Judge punishes hedging.
  - This single question is almost certainly a −1q regression.

## Predicted impact

- 13 format-equivalent → 0 net (judge tolerant)
- 9 real disagreements → ~4-5 wins, ~4-5 losses (coin flip)
- 1 hedging regression → −1 confirmed
- **Best case: +4-5 wins − 5-6 losses = −1 to 0**
- **Worst case: −1 confirmed + 9 losses = up to −5 (if all coin flips lose)**
- **Most likely net on L2: −2 to +1**, with downside risk from cerebrum-DNR
  hedging case

This is structurally similar to sub_006 SC k=3: ~25% answer churn, ~50% format
equivalence, with 1 cerebrum-DNR regression baked in. The L4 win pattern does
**not** appear to transfer cleanly to L2 because L2 has problem text that
already gives structure; the new template's marginal value (in-image numerics)
is modest.

## Audit fixes applied (3)

3 L5 lowercase → uppercase (carry-over, idempotent).

## Cost

~$420 actual (138 questions × $3 avg, Gemini-3.1-Pro for caption + reason +
critic). Cumulative experiment spend ~$2700.

## Files

- `submission.zip` — built from prediction_audited.csv (= renamed inside zip)
- `prediction.csv` = `prediction_audited.csv`
- `prediction_pre_audit.csv` — raw output before audit
- `prediction_private.csv` — empty
- `audit_report.md`
- `prediction_result.zip` / `scoring_result.zip` — pending Codabench scoring

## Going forward

Decision points:
1. **If sub_007 confirms ≈ −1 to 0**, L2 caption template is dead — L4 pattern
   does not transfer. Pivot to **L1 few-shot** (Task #46, ~$160).
2. **If sub_007 surprises with +3 or more**, run L3 with same template (Task ~$440).
3. The 1 hedging regression should be addressable by adding "DO NOT use
   'Cannot be determined' or hedging language" to the L2 reason or critic prompt.

## Lesson (preliminary, to confirm post-upload)

L4-style verbatim caption requires **input/output mismatch** (text empty → image
is everything). For L2 where text already exists, forcing more in-image
extraction adds caption length but doesn't unlock new physics — the solver
already had what it needed. Pattern transfer from sub_004 looks weak.
