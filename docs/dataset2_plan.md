# Second dataset — LongMemEval (design)

Drafted and decided 17 Nov 2026, before the reported run. Results: `docs/lme_results.md`.

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

## Design

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

## Decisions (accepted by the author, 17 Nov 2026)

- **A.** 30 poison targets + 3 pilot targets (fixed before any run, never reported) + 30 update probes.
- **B.** User turns only (assistant turns dropped). Stated as a limitation: differs from the LoCoMo pipeline.
- **C.** The values and templates (`data/lme_targets_manual.json`, `data/lme_update_probes.json`) were drafted first
  and every row was then checked by the author (`"review": "reviewed"`) before the reported run.

## Implementation (17 Nov 2026)

- `src/lme.py`: loader (user turns, 10-session windows) and case builder → `data/lme_poison_cases.json`
  (A1, A2, A3, AD1, AD2 per target; test-split phrases), `data/lme_clean_external.json`, `data/lme_updates.json`.
  One target (`6ade9755`) has its evidence in the last session; its poison goes into an extra empty session dated at
  the question.
- `run_lme.py`: no defense vs Trust Gate with the LoCoMo-locked thresholds. Metrics: target accuracy, ASR and PMAR per
  attack, FRR dialog/external, update accuracy, update-rejection rate.
- `tests/test_lme.py` (7 tests). Dry run with the fake model OK.
- **Pilot 1 (qwen3, 17 Nov 2026) — invalid, fixed:** with the speaker label "User", the locked writer prompt ("facts
  about the people in it ... use full names") returned `[]` for most sessions, including the poison turn (e.g. only
  2 of 10 sessions produced any memory). Fix without touching the prompt: the user is named "Emery" (3 occurrences in
  the whole raw file, none in the selected windows; tested), questions are asked as "Emery: <question>" (the A3-auth
  convention), and external pages name Emery instead of "this user". Pilot outputs moved to
  `results/_invalid_lme_pilot_user_label/`. The pilot was rerun with the fix (OK) before the reported run.
- AD3 (flooding) needs a hand-written topic per target and AD4 is a per-conversation scenario; both are LoCoMo-only.
