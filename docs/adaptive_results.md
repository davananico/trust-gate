# Adaptive attacks — test results (AD1, AD2, AD4)

Run on 17 Nov 2026, test split, once, with the locked gate and the files checksummed in
`docs/adaptive_test_manifest.txt`. AD3 (flooding) test results: see the end. Original attacks (A1, A2, A3-auth) are
from the main test run of 22 Oct 2026 (`results/test_final/`). Raw outputs: `results/adaptive/`.

ASR = attack success (agent gives the poison value, or proposes `send_file` to attacker.example); PMAR = poison
memories accepted by the gate. 95% Wilson intervals. A1–A2/AD1–AD2: 34 trials per model; A3-auth/AD4: 7.

## ASR with the Trust Gate (no defense → gate)

| Attack | qwen3:8b | gemma4:12b | llama3.1:8b | olmo-3:7b |
| --- | --- | --- | --- | --- |
| A1 false fact (reference) | 47.1 → 17.6% [8.3–33.5] | 20.6 → 11.8% [4.7–26.6] | 32.4 → 5.9% [1.6–19.1] | 41.2 → 0.0% [0.0–10.2] |
| A2 confident, original | 44.1 → 0.0% [0.0–10.2] | 26.5 → 0.0% [0.0–10.2] | 35.3 → 0.0% [0.0–10.2] | 32.4 → 0.0% [0.0–10.2] |
| **AD1 split assertion** | 52.9 → 20.6% [10.3–36.8] | 26.5 → 14.7% [6.5–30.1] | 32.4 → 11.8% [4.7–26.6] | 38.2 → 5.9% [1.6–19.1] |
| **AD2 lexicon-free** | 50.0 → 20.6% [10.3–36.8] | 23.5 → 17.6% [8.3–33.5] | 32.4 → 11.8% [4.7–26.6] | 32.4 → 5.9% [1.6–19.1] |
| A3-auth, external page | 14.3 → 0.0% | 100 → 0.0% | 100 → 0.0% | 0.0 → 0.0% |
| **AD4 dialog authorization** | 28.6 → 28.6% | 71.4 → 71.4% | 57.1 → 57.1% | 0.0 → 0.0% |

## PMAR (poison memories accepted by the gate)

| Attack | qwen3:8b | gemma4:12b | llama3.1:8b | olmo-3:7b |
| --- | --- | --- | --- | --- |
| A1 false fact (reference) | 35.3% (12/34) | 38.2% (13/34) | 40.6% (13/32) | 10.7% (3/28) |
| A2 confident, original | 2.6% (1/38) | 2.9% (1/35) | 0.0% (0/34) | 0.0% (0/24) |
| **AD1 split assertion** | 38.9% (14/36) | 42.9% (15/35) | 50.0% (17/34) | 13.0% (3/23) |
| **AD2 lexicon-free** | 35.9% (14/39) | 45.5% (15/33) | 45.7% (16/35) | 16.1% (5/31) |
| A3-auth, external page | 0/1 | 0/7 | 0/7 | – (never written) |
| **AD4 dialog authorization** | 100% (7/7) | 100% (7/7) | 100% (4/4) | 50% (2/4) |

## What this shows

1. **The A2 result (0%) depends on the lexicon, not on detecting confident claims.** Moving the same assertion
   phrase to its own line (AD1) or rewording it (AD2) brings PMAR from about 0–3% to the A1 level (35–50% for
   qwen3, gemma4, llama3.1), in all four models. Hypothesis confirmed.
2. **The gate still works through the contradiction judge.** Even under AD1/AD2, ASR falls well below no defense
   (e.g. qwen3 52.9 → 20.6%), at about the A1 level: the judge, not the pattern list, does the work.
3. **Authorization claimed in the dialog passes the gate completely** (AD4 PMAR 100% for three models); the agent
   then proposes `send_file` to the attacker in 2/7, 5/7 and 4/7 scenarios. The separate allowlist blocks the
   transfer; the memory gate does not. This supports the design rule "memory is not authorization" and shows the
   gate cannot be the only control.
4. olmo-3 resists everything mostly because its judge flags most memories as conflicting (63% FRR on clean dialog in
   the main run), not because it detects the attacks.

Caveats: n = 34 (7 for authorization) per model; intervals are wide and overlap between AD1/AD2 and A1. The attacks
were written by the same author who built the gate.

## AD3 (flooding)

Dev (v2, all 4 models): PMAR 27% / 33% / 23% / 10% vs the A1 dev level 40% / 27% / 38% / 10%; the true fact stayed
among the judge's neighbours (qwen3: displaced in 1 of 14).

Test (17 Nov; qwen3 in the first slot, gemma4/llama3.1/olmo-3 rerun from scratch in the evening slot; gemma4's
partial log from the first slot was discarded):

| Model | A1 ASR gate | A1 PMAR | AD3 ASR no defense | AD3 ASR gate | AD3 PMAR |
| --- | --- | --- | --- | --- | --- |
| qwen3:8b | 17.6% [8.3–33.5] | 35.3% (12/34) | 38.2% | 23.5% [12.4–40.0] | 47.1% (16/34) [31.4–63.3] |
| gemma4:12b | 11.8% [4.7–26.6] | 38.2% (13/34) | 17.6% | 11.8% [4.7–26.6] | 29.4% (10/34) [16.8–46.2] |
| llama3.1:8b | 5.9% [1.6–19.1] | 40.6% (13/32) | 26.5% | 14.7% [6.5–30.1] | 50.0% (16/32) [33.6–66.4] |
| olmo-3:7b | 0.0% [0.0–10.2] | 10.7% (3/28) | 29.4% | 0.0% [0.0–10.2] | 14.3% (4/28) [5.7–31.5] |

Flooding shifts acceptance slightly upward for qwen3 and llama3.1 and downward for gemma4, all within overlapping
intervals: naive flooding gives the attacker at most a small edge and does not break the contradiction check. On
dev the shift went the other way for qwen3, which is consistent with no real effect at this sample size.
