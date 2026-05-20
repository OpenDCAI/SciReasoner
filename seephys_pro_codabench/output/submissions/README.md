# Submissions Log — SeePhys Pro Codabench 16010

## Convention

Each submission lives in its own folder under `output/submissions/sub_NNN_<short-tag>/`:

```
sub_NNN_<tag>/
├── notes.md                # config, score, lessons learned
├── submission.zip          # what we uploaded
├── prediction.csv          # public testmini predictions
├── prediction_private.csv  # private test predictions (empty until we run test split)
├── prediction_result.zip   # what Codabench echoed back (after scoring)
└── scoring_result.zip      # Codabench's scores.json + diagnostics.json
```

After each upload, **before the next experiment**:

1. Save `submission.zip`, `prediction.csv`, `prediction_private.csv` into the folder
2. Once Codabench finishes scoring, download `prediction_result.zip` + `scoring_result.zip` and drop them in
3. Edit `notes.md`: per-level score, what changed in pipeline, lessons learned
4. Update the Index table below

## Index — exact scores from scoring_result.zip

| # | Tag | Submitted | **Overall** | L1 | L2 | L3 | L4 | L5 | local_correct | items_to_llm | Notes |
|--:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `sub_001_gemini_baseline`        | 16:06 | 0.7651 | 0.770 | 0.810 | 0.755 | 0.700 | 0.933 | 598/699 | 131 | Pure Gemini-3.1-Pro pipeline |
| 2 | `sub_002_gpt5.5_critic_audited`  | 17:59 | 0.7012 ❌ | 0.725 | 0.715 | 0.700 | 0.635 | 0.900 | 549/660 | 170 | gpt-5.5 critic — −53q regression |
| 3 | `sub_003_gemini_audited`         | 18:04 | **0.7663** ✓ | 0.770 | 0.800 | 0.765 | 0.705 | 0.933 | 599/700 | 130 | Rollback + 6 format fixes; #1 |
| 4 | `sub_004_l4_recaption`           | 21:30 | **0.7747** ✓✓ | 0.765 | 0.810 | 0.760 | **0.740** | 0.933 | 612/706 | 124 | L4-specific verbatim-OCR caption; **+7q real signal on L4** |
| 5 | `sub_005_l1_promptv3`            | 23:09 | 0.7735 | 0.765 | 0.800 | 0.760 | 0.745 | 0.933 | 617/710 | 120 | L1 prompt rules (no-hedge, natural units, canonical form). **L1 unchanged** despite 40 answer rewrites; judge is form-tolerant; net −1q overall (L2 noise) |
| 6 | `sub_006_l1_sc3`                 | 13:10 | 0.7735 | 0.760 | 0.805 | 0.760 | 0.745 | 0.933 | 615/709 | 121 | L1 SC k=3 @ T=0.7. **L1 −1q (real)**: 75% unanimous votes — model already too stable for SC to help. Net −1q overall, exactly matching gpt-5.4 referee prediction. Cost ~$160 |
| 7 | `sub_007_l2_caption`             | not uploaded | predicted ~0.7723–0.7758 | 0.765 | ~0.805–0.815 | 0.760 | 0.740 | 0.933 | — | — | L2 verbatim caption (L23 hybrid template). 23/138 answers changed; 13 are format-equiv, 9 are coin-flip disagreements, 1 confirmed hedging regression (cerebrum DNR). Caption +35% chars. Cost ~$420. **Held**: 1 confirmed hedging regression + L4 pattern weak transfer to L2 |
| 8 | `sub_008_l1_fewshot`             | 15:20 | **0.7771** ✓✓✓ | **0.770** | 0.800 | 0.765 | 0.750 | 0.933 | 613/707 | 121 | L1 reason prompt with 3 worked physics examples. **L1 +1q (noise-floor)**, other levels +1q net (pure judge noise). **NEW BEST** = sub_004 + 0.24pp. Cost ~$280 |

(Each correct question on testmini = 1/830 ≈ 0.0012 of overall; each on a 200-question level = 0.005.)

## Codabench daily limit

Max 5 submissions per day. **Used 3/5 on 2026-05-19. Used 2/5 on 2026-05-20 (sub_006, sub_008). 3 left today.**

## Confirmed signals

- **L4-specific verbatim-OCR caption (sub_004)**: real **+7 questions on L4** (0.705 → 0.740). First confirmed real-signal improvement above noise. Cost: ~$330.
- **L4 truncation fallback (audit)**: real **+1 question** (sub_003 vs sub_001 on L4). Cost: $0.
- **L5 multichoice case fix**: net 0. **Judge appears case-insensitive** on multichoice answers.
- **Heterogeneous critic (sub_002)**: real **−53 questions**. gpt-5.5 hedging + format drift; judge punishes both.
- **Format prompt rules on Gemini reason (sub_005)**: 0 effect on accuracy — judge is form-tolerant. local_correct ↑18, items_to_llm ↓10, but final score unchanged. 40 L1 rewrites for net 0.
- **L1 SC k=3 (sub_006)**: real **−1 question on L1** (0.765 → 0.760). 75% of L1 already converges 3-0 unanimous at T=0.7; SC has no headroom. gpt-5.4 referee predicted −1 exactly. Cost: ~$160 wasted. **Same-model SC at low temperature is dead.**
- **L1 few-shot worked examples (sub_008)**: marginal **+1 question on L1** (0.765 → 0.770), at the noise floor. 75% of the 51 answer changes were pure format mimicry of the examples (`\mathrm{...}` wraps, `\frac` rewrites). The 25% that were real disagreements landed slightly better than coin-flip. Net **+2 overall** (with judge noise on untouched levels). Cost: ~$280. **Cannot strongly replicate, but pushed us to NEW BEST 0.7771.**

## Confirmed noise

- **±1-2 question swings on levels not touched** by the audit: deepseek/deepseek-v4-pro semantic judge has nondeterministic borderline calls.
  - **Rule of thumb: need ≥3pp / ≥6 questions per 200 to declare a real change**.

## What's stably true

- Gemini-3.1-Pro three-stage pipeline + L4-specific caption + **L1 few-shot reason prompt** = **0.7771** (645/830 correct) ← current best
- L1 (text-only) = 0.770; few-shot moved this from 0.765 (marginal +1q at noise floor, not strongly replicable)
- L2 / L3 / L5: stable at 0.800–0.810 / 0.760–0.765 / 0.933 — all leading or tied with ctree
- L4 (visual): stable at 0.740–0.750 with verbatim caption — caught up to ctree's 0.75
- **Remaining gap to ctree**: 0.78 − 0.7771 = 2-3 questions, all in L1 (we have 0.770 vs ctree's 0.79)

## Things to try next (prioritized)

1. **L2/L3 verbatim caption template** (mirror sub_004's L4 win). L2 has heavy diagrams + values; L3 likewise. Cost ~$200, ROI uncertain but proven pattern.
2. **Few-shot worked physics examples** in L1 reason prompt (target reasoning, not formatting). Cost ~$160 for L1 only.
3. **High-T SC k=5** with chain-of-thought diversification (force different solution paths, vote). Cost ~$300, ROI uncertain — sub_006 showed model is already deterministic at T=0.7.
4. **Domain-routed prompts** for L1 (mech / EM / thermo / optics each get tailored system prompt). Cost ~$160 for L1.
5. **Run private leaderboard** (3320 questions) — **mandatory for prize**. Cost ~$6000.

## Things abandoned

- ~~Heterogeneous critic~~ — proven harmful in sub_002.
- ~~Jury voting~~ — same family of problem (different model = different format priors). Jurors data is preserved in `output/v2_pub830/jury/` but not used.
- ~~L1 format prompt rules (v3)~~ — sub_005 confirmed 0 score impact.
- ~~Heterogeneous L1 reason swap (gpt-5.5)~~ — referee predicted −16q, never submitted.
- ~~Same-model SC k=3 @ T=0.7 on L1~~ — sub_006 confirmed real −1q. Model is too deterministic for low-T SC to add value.
