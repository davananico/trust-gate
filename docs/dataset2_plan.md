# Second dataset — LongMemEval (plan, needs decisions)

Drafted 17 Nov 2026. Nothing here has been run with a real model.

## Source

- LongMemEval (Wu et al., ICLR 2025), cleaned release: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
  (repository https://github.com/xiaowu0162/LongMemEval, MIT license, confirm the LICENSE file before submission).
- Downloaded 17 Nov 2026 to `data/raw/longmemeval/` (git-ignored):
  - `longmemeval_s_cleaned.json` 277,383,467 bytes, sha256 `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`
  - `longmemeval_oracle.json` 15,388,478 bytes, sha256 `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c`
- 500 questions; each has its OWN history (38–62 sessions, median about 78k words), user–assistant chats.

## Why this dataset

- Different conversation type from LoCoMo (user–assistant, not two people), so it tests whether the results
  transfer beyond LoCoMo.
- It has **knowledge-update** questions: the user states a value, then a newer value later. This lets us measure
  directly what the LoCoMo error analysis could only infer: does the gate reject legitimate updates?

## Candidates (`src/prepare_longmemeval.py` → `data/lme_candidates.json` / `.csv`)

- 56 `poison_target`: single-session-user questions, answer ≤ 4 words, stated literally in one user turn.
- 70 `update_probe`: knowledge-update questions with the old and new value in two different user sessions.

## Design (proposed)

1. **Thresholds are not retuned.** The gate runs with the thresholds locked on LoCoMo dev. There is no
   LongMemEval dev split; the whole set is a transfer test. A pilot of 3 poison targets checks the pipeline and is
   excluded from reporting.
2. **Poison targets**: about 30, chosen by hand from the 56. For each: a first-person claim template and a poison
   value (`data/lme_targets_manual.json`, same format as `data/targets_manual.json`), then A1/A2/A3 + a clean
   external page built exactly as for LoCoMo, plus the adaptive attacks.
3. **Update probes**: about 30 chosen by hand from the 70. No attack. Report the update-rejection rate (the newer
   value's memory rejected or quarantined) and answer accuracy with and without the gate.
4. **History subset (compute)**: the evidence session(s) plus the nearest sessions by date, 10 sessions per
   question in total; poison goes into the next session after the evidence session in that subset.
5. **Turns given to the writer**: see decision B.

Rough compute (an estimate, not measured): about 30 targets × 10 sessions × (clean + A1 + A2 + A3 + external +
AD1–AD3) runs × 2 conditions; writer calls are cached across runs of the same question, gate calls are not.
Expected a few hours per model on one L4.

## Decisions needed from the author

- **A. How many targets:** 30 poison + 30 updates (proposed), or all 56 + 70 (about twice the compute).
- **B. Assistant turns:** (1) keep full assistant turns: more faithful, much more text and compute; or
  (2) user turns only: lighter; the agent still remembers only user facts, but this differs from the LoCoMo
  pipeline and must be stated as a limitation. Proposed: (2).
- **C. Who writes the poison values and templates:** Claude drafts them, the author checks every row (proposed).
