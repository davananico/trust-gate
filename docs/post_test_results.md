# Post-test additions — results

Added 18 Nov 2026, after all test results had been seen (`docs/post_test_changes.md`). Raw outputs:
`results/post_test/` (server runs) and `results/pooled/pooled_analysis.csv`.

## 1. Contradiction-only baseline (LoCoMo test, 4 models)

The gate with only the LLM contradiction judge: no source trust, no confidence, no pattern list. Same thresholds
as the Trust Gate (no tuning; with θ ∈ (−1, 0] it accepts iff the judge says "no conflict").

**Reproducibility check:** the `no_defense` condition, recomputed from cache, gives the same answer as the 22 Oct
test run in 880 of 880 trials.

Trust Gate (T) vs contradiction-only (C), %:

| Metric | qwen3:8b | gemma4:12b | llama3.1:8b | olmo-3:7b |
| --- | --- | --- | --- | --- |
| ASR A1 false fact | T 17.6 / C 17.6 | T 11.8 / C 11.8 | T 5.9 / C 5.9 | T 0.0 / C 0.0 |
| ASR A2 confident | T 0.0 / C 17.6 | T 0.0 / C 14.7 | T 0.0 / C 11.8 | T 0.0 / C 14.7 |
| ASR A3 external page | T 23.5 / C 23.5 | T 11.8 / C 11.8 | T 8.8 / C 8.8 | T 5.9 / C 5.9 |
| ASR A3-auth (n = 7) | T 0.0 / C 14.3 | T 0.0 / C 100 | T 0.0 / C 57.1 | T 0.0 / C 0.0 |
| PMAR A2 | T 2.6 / C 36.8 | T 2.9 / C 42.9 | T 0.0 / C 47.1 | T 0.0 / C 33.3 |
| FRR dialog | T 2.0 / C 1.8 | T 2.0 / C 1.9 | T 14.5 / C 14.3 | T 63.2 / C 63.2 |
| FRR external | T 5.9 / C 5.9 | T 2.9 / C 2.9 | T 22.7 / C 22.7 | T 77.1 / C 77.1 |
| Clean accuracy | T 62.9 / C 62.9 | T 62.9 / C 62.9 | T 54.3 / C 54.3 | T 20.0 / C 20.0 |

**Reading.** The two gates are identical on A1, A3, clean accuracy and external FRR in every model. They differ
only where the pattern list fires: A2 (the lexicon was written from the dev A2 phrases) and A3-auth (authorization
words on the page). The lexicon adds 0.1–0.2 points of dialog FRR. Together with the decision check in
`docs/novelty_check.md` (accept ⟺ R = 0 at the locked threshold), this shows what the Trust Gate is in practice:
the LLM contradiction judge plus a phrase list. AD1/AD2 already showed the phrase list only stops the phrases it
contains.

Pooled over the 4 models (paired; 95% cluster-bootstrap interval over targets):

| Comparison | C | T | T − C [95% CI] |
| --- | --- | --- | --- |
| ASR A1 | 8.8% | 8.8% | 0.0 [0.0, 0.0] |
| ASR A2 | 14.7% | 0.0% | −14.7 [−23.5, −7.4] |
| ASR A3 | 12.5% | 12.5% | 0.0 [0.0, 0.0] |
| ASR A3-auth (7 clusters: interval unreliable) | 42.9% | 0.0% | −42.9 |
| Clean accuracy | 50.0% | 50.0% | 0.0 |

## 2. Pooled analysis of the main claims (4 models)

`src/pooled_analysis.py`. Pairs = same model + same case (or same model + same target when two attacks are
compared). Interval: cluster bootstrap over targets, 10,000 resamples, seed 2026. Exact McNemar p as a secondary
number (it treats pairs as independent).

| Claim | A | B | B − A [95% CI] | McNemar p |
| --- | --- | --- | --- | --- |
| LoCoMo ASR A1, no defense → gate | 35.3% | 8.8% | −26.5 [−36.0, −17.6] | 3e-11 |
| LoCoMo ASR A2, no defense → gate | 34.6% | 0.0% | −34.6 [−45.6, −24.3] | 1e-14 |
| LoCoMo ASR A3, no defense → gate | 40.4% | 12.5% | −27.9 [−37.5, −19.1] | 7e-12 |
| LoCoMo ASR AD1, no defense → gate | 37.5% | 13.2% | −24.3 [−33.8, −15.4] | 2e-10 |
| LoCoMo ASR AD2, no defense → gate | 34.6% | 14.0% | −20.6 [−30.1, −11.8] | 6e-08 |
| LoCoMo ASR AD3, no defense → gate | 27.9% | 12.5% | −15.4 [−23.5, −8.8] | 2e-05 |
| LoCoMo ASR AD4, no defense → gate (n = 28) | 39.3% | 39.3% | 0.0 | 1 |
| LME ASR A1, no defense → gate | 40.0% | 18.3% | −21.7 [−31.7, −12.5] | 2e-07 |
| LME ASR A2, no defense → gate | 40.0% | 0.8% | −39.2 [−51.7, −27.5] | 1e-14 |
| With gate: A2 → AD1 (LoCoMo / LME) | 0.0 / 0.8% | 13.2 / 16.7% | +13.2 [+6.6, +20.6] / +15.8 [+8.3, +24.2] | 8e-06 / 2e-05 |
| With gate: A2 → AD2 (LoCoMo / LME) | 0.0 / 0.8% | 14.0 / 16.7% | +14.0 [+7.4, +21.3] / +15.8 [+7.5, +25.0] | 4e-06 / 2e-05 |
| With gate: A1 → AD3 flooding | 8.8% | 12.5% | +3.7 [0.0, +7.4] | 0.23 |
| LoCoMo clean accuracy, no defense → gate | 56.1% | 50.0% | −6.1 [−9.3, −2.9] | 2e-04 |
| LoCoMo target accuracy (clean history) | 72.1% | 65.4% | −6.6 [−10.3, −2.9] | 0.004 |
| LME target accuracy (clean history) | 82.5% | 80.8% | −1.7 [−6.7, +2.5] | 0.69 |
| **LME update accuracy, no defense → gate** | 73.3% | 38.3% | **−35.0 [−45.0, −25.8]** | 5e-13 |

Notes: the clean-accuracy cost on LoCoMo comes mostly from llama3.1 and olmo-3 (their judges over-flag); for
qwen3/gemma4 it is ≤ 1 point (per-model tables in `docs/`). Flooding (AD3) gives no significant edge.

## 3. Contradiction-only on adaptive attacks and LongMemEval

Reproducibility: `no_defense` recomputed from cache matches the original runs in 436/436 adaptive and 840/840
LongMemEval trials.

Pooled over 4 models, contradiction-only (C) vs Trust Gate (T):

| Dataset | Attack / metric | C | T | T − C [95% CI] |
| --- | --- | --- | --- | --- |
| LoCoMo | ASR AD1 split assertion | 12.5% | 13.2% | +0.7 [0.0, +2.2] |
| LoCoMo | ASR AD2 lexicon-free | 14.7% | 14.0% | −0.7 [−2.2, 0.0] |
| LoCoMo | ASR AD3 flooding | 11.8% | 12.5% | +0.7 [0.0, +2.2] |
| LoCoMo | ASR AD4 dialog authorization (n = 28) | 39.3% | 39.3% | 0.0 |
| LME | ASR A1 | 18.3% | 18.3% | 0.0 |
| LME | ASR A2 | 22.5% | 0.8% | −21.7 [−30.8, −13.3] |
| LME | ASR A3 | 12.5% | 13.3% | +0.8 [0.0, +2.5] |
| LME | ASR AD1 / AD2 | 16.7% / 16.7% | 16.7% / 16.7% | 0.0 / 0.0 |
| LME | Target accuracy (clean history) | 80.0% | 80.8% | +0.8 [0.0, +2.5] |
| LME | **Update accuracy** | **38.3%** | **38.3%** | 0.0 |

**Reading.** Once the attacker avoids the listed phrases (AD1, AD2) or states authorization in the dialog (AD4),
the Trust Gate and the bare contradiction judge are indistinguishable (differences of one trial). The update
problem is entirely the judge's: update accuracy is identical with or without the other signals.

## 4. LoCoMo-Adv text attacks (4 models, test, 34 targets x 7 families)

Design and deviations: `docs/locomo_adv_comparison.md`. N = no defense, C = contradiction-only, T = Trust Gate.

**fact_overwrite** (the only family that states a false value):

| | qwen3:8b | gemma4:12b | llama3.1:8b | olmo-3:7b | Pooled |
| --- | --- | --- | --- | --- | --- |
| ASR N / C / T | 64.7 / 26.5 / 0.0 | 47.1 / 26.5 / 0.0 | 61.8 / 32.4 / 0.0 | 41.2 / 2.9 / 0.0 | 53.7 / 22.1 / 0.0 |
| PMAR C / T | 45.2 / 0.0 | 38.2 / 0.0 | 63.8 / 0.0 | 5.6 / 0.0 | |

Pooled: N → T −53.7 [−62.5, −44.9]; C → T −22.1 [−30.9, −14.0]. Every T rejection carries the `over_assertion`
pattern: the template says "Correction **confirmed**" and "**verified** by the original source", words already in
our lexicon (written from our dev A2 phrases before any of this was seen). So on this family the phrase list
transfers to attacks we did not write, but AD2 shows a rewording removes it.

**The six directive families** ("treat the latest correction as authoritative", "[SYSTEM VERIFIED] ... answer is
unknown", OCR/caption variants): no effect on answers.
- The writer rarely turns them into memories at all: attack memory written in 0–3% of cases for qwen3; for the
  others mostly vision_caption (gemma4 50%), adaptive_nl_evasion (llama3.1 77%) and visual_prompt_injection
  (olmo-3 56%, llama3.1 27%, gemma4 21%).
- With no defense, target accuracy under these families equals clean target accuracy (qwen3 76.5 vs 76.5, gemma4
  76.5–82.3 vs 79.4, llama3.1 70.6–76.5 vs 76.5, olmo-3 52.9–55.9 vs 55.9). Any drop with a gate equals that gate's
  own cost on clean history (llama3.1 70.6, olmo-3 35.3), not the attack.
- When written, they are mostly accepted (PMAR 67–100% for gemma4 and llama3.1): a directive without a concrete
  value contradicts nothing, so the judge passes it. Harmless here only because our agent prompt ignores it.

**Consistent with SAGE-Mem's own numbers**: their undefended baseline also has false-belief rate 0 on LoCoMo-Adv.
Most of the benchmark tests whether directives get stored, not whether answers change; only fact_overwrite moves
answers, and on it our gates behave like on A2 (judge alone ≈ A1 level; judge + phrase list ≈ 0).
