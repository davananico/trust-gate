# Second dataset (LongMemEval) — results

Run 17 Nov 2026 (evening GPU slot), 4 models, no defense vs the Trust Gate with the thresholds **locked on LoCoMo
dev** (no retuning: a transfer test). 30 poison targets + 30 knowledge-update probes, reviewed by the author before
the run (`docs/lme_review_*.csv`); 3 pilot targets excluded. Design and limitations: `docs/dataset2_plan.md`
(user turns only, 10-session windows, user named "Emery"). Raw outputs: `results/lme/`. 95% Wilson intervals;
n = 30 trials per attack per model.

## Poison: ASR no defense → Trust Gate

| Attack | qwen3:8b | gemma4:12b | llama3.1:8b | olmo-3:7b |
| --- | --- | --- | --- | --- |
| A1 false fact | 43.3 → 20.0% [9.5–37.3] | 40.0 → 10.0% [3.5–25.6] | 50.0 → 40.0% [24.6–57.7] | 26.7 → 3.3% [0.6–16.7] |
| A2 confident | 50.0 → 0.0% [0.0–11.3] | 36.7 → 0.0% [0.0–11.3] | 46.7 → 0.0% [0.0–11.3] | 26.7 → 3.3% [0.6–16.7] |
| A3 external page | 56.7 → 20.0% [9.5–37.3] | 30.0 → 6.7% [1.8–21.3] | 16.7 → 16.7% [7.3–33.6] | 60.0 → 10.0% [3.5–25.6] |
| AD1 split assertion | 46.7 → 20.0% | 40.0 → 10.0% | 40.0 → 30.0% | 23.3 → 6.7% |
| AD2 lexicon-free | 43.3 → 16.7% | 30.0 → 10.0% | 43.3 → 26.7% | 26.7 → 13.3% |

PMAR (poison accepted): A1 35% / 17% / 67% / 15%; A2 0% / 0% / 0% / 7%; AD1 32% / 17% / 60% / 17%;
AD2 30% / 21% / 52% / 38% (qwen3 / gemma4 / llama3.1 / olmo-3).

## Utility

| | qwen3:8b | gemma4:12b | llama3.1:8b | olmo-3:7b |
| --- | --- | --- | --- | --- |
| Target accuracy, clean history (no defense → gate) | 90 → 90% | 97 → 97% | 83 → 83% | 60 → 53% |
| FRR dialog | 0.4% (7/1674) | 0.4% (4/1133) | 2.1% (18/850) | 5.7% (63/1116) |
| FRR external | 10.3% (3/29) | 3.3% (1/30) | 0.0% (0/13) | 75.9% (22/29) |
| **Update rejection** (newer value held back) | **35.9%** (14/39) [22.7–51.6] | **54.8%** (17/31) [37.8–70.8] | **34.3%** (12/35) [20.8–50.8] | **56.7%** (17/30) [39.2–72.6] |
| **Update accuracy** (no defense → gate) | **73 → 43%** | **83 → 30%** | **87 → 60%** | **50 → 20%** |

## What this shows

1. **The poison results transfer.** With thresholds tuned only on LoCoMo, the gate lowers ASR on a different
   conversation type for three of four models (llama3.1 is the exception: its judge accepts 67% of A1 poison), A2
   falls to 0–3%, and AD1/AD2 again bring poison back to about the A1 level (the lexicon finding replicates).
2. **Ordinary clean memories are almost never held back** (FRR dialog 0.4–2.1% for qwen3, gemma4, llama3.1).
3. **The cost is concentrated on legitimate updates.** 34–57% of memories carrying a newer value are held back, and
   accuracy on update questions falls by 27–53 points, in all four models. The contradiction judge treats "the value
   changed" like "the value is false". This measures directly the failure mode inferred from the LoCoMo error
   analysis (poison, updates and recurring events look alike to a write-time check).
4. olmo-3 again behaves as an over-eager judge (76% FRR on clean external pages).

## Time factor (exploratory, not tuned; `results/lme/lme_time_sensitivity.txt`)

Decisions recomputed from logged signals with age = question date − session date, λ_t ∈ {0, 0.001, 0.01},
θ ∈ {−0.05, 0.1, 0.2, 0.3}. At the locked θ = −0.05 no decision changes for any λ_t (as derived: R = 0 → accept,
R = 1 → reject). Only at θ = 0.3 with λ_t ≥ 0.001 does time matter, and only for low-trust external sources: clean
external pages held back jump from 3–10% to 83–90%, while poison held back rises by 3–6 points. **Update rejection
does not change at any setting**: rejected updates were flagged by the judge (R = 1), which a time factor cannot
undo. In this formula, time decay is not a remedy for the update problem.

## Caveats

n = 30 per attack per model; user turns only and 10-session windows (not the full LongMemEval haystack); poison
values and templates drafted by an AI assistant and checked by the author; the writer did not record some poisons (e.g.
qwen3 recorded 20 of 30 A1 poisons); olmo-3 writer: 2 unreadable replies of about 4,600.
