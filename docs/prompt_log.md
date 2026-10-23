# Gate prompt history

Every prompt change was made **on dev data only** and frozen before the gate was run on test data.
Numbers below: qwen3:8b, dev split, active memory = memories from sessions before the injection session, 5 nearest neighbors.
"Clean" = up to 4 clean memories per case from the same injection session (n = 178).

## gate_contradiction

| Version | Core question | A1 YES | A2 YES | A3 YES | Clean YES |
| --- | --- | --- | --- | --- | --- |
| v1 (`prompts/archive/gate_contradiction_v1.txt`) | "cannot both be true"; "new facts or extra details are NOT contradictions" | 27% | 31% | 60% | 1.1% |
| **v2 (in use, frozen 19 Oct 2026)** | "would give a DIFFERENT answer to the same question" | **60%** | **63%** | **80%** | **2.8%** |

Reason for the change: diagnosing v1 on the 15 dev A1 poisons -> 4 caught, 8 "LLM did not notice" although the true
fact was among the 5 neighbors (e.g. "favorite recipe is beef stew" vs "... is Chicken Pot Pie"), 2 true facts not
retrieved, 1 true fact never written by the writer. **Limitation:** the attribute examples in v2 (favorite thing, book,
car, pet, job, injury, place, date) were inspired by v1's errors on dev data.

## gate_confidence

v1 (in use, frozen 19 Oct 2026). On dev: A1/A2/A3 poison average 0.93 / 1.00 / 1.00; clean 0.85. Confidence does not
separate poison (the poison sentence really is in its source text); its role is to catch writer errors, not poison.
