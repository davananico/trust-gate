# Changes made after the test run

The test split was run on 22 Oct 2026 (checksums of every locked file: `docs/test_run_manifest.txt`).
Any later change to a locked file is listed here, with evidence that it does not affect the results.

## 23 Oct 2026 — English translation (non-functional)

**What changed:** comments, docstrings, printed messages, test names, figure labels and the YAML/`.env.example`
comments were translated from Indonesian to English. `docs/spesifikasi_eksperimen.md` was translated, brought up to
date with the locked settings, and renamed to `docs/experiment_spec.md`; `docs/prompt_log.md` and `README.md` were
translated and updated.

**What did not change:** prompts (already English), data files, thresholds, config values, and program logic.
The manifest checksums no longer match for the translated files; this is expected.

**Evidence that the change is non-functional:**
- Python files: the AST of every file before and after translation is identical after removing docstrings and
  replacing string literals with a placeholder (comments are not part of the AST). 31 of 33 files matched directly;
  the other two differed only by a renamed local variable (`racun` -> `poison` in `src/demo.py`, `beda` -> `diff` in
  `tests/test_week1.py`) and matched after applying that rename to the old file. Every changed string literal was
  reviewed: all are human-readable messages (prints, error messages, the fake tool's status/detail text); none is a
  SQL statement, regex, data key or prompt.
- YAML files: `yaml.safe_load` returns identical values before and after.
- Test suite: 52 passed after the change.
- Figures were regenerated from the unchanged result files; only labels changed (the content-only gate code "K" became "C").

## 18 Nov 2026 — contradiction-only baseline, pooled analysis, LoCoMo-Adv comparison (additions)

Added after every test result had been seen, at the author's request, to answer reviewer questions. All are
**additions**: the Trust Gate, its thresholds, prompts, data and earlier outputs are unchanged, and they are
reported as post-hoc in the paper.

**What changed:**
- `src/gate/trust_gate.py`: new `GateParams.mode = "contradiction_only"` (score = −λ_r · R_contradiction; no source
  trust, no confidence, no pattern list). `needs_contradiction` is also true for this mode. The `trust` and
  `content_only` branches are untouched.
- `config/experiment.yaml`: new variant `contradiction_only` (Trust Gate thresholds; `default: false`, so the
  default run is unchanged). With θ ∈ (−1, 0] it accepts iff the judge says "no conflict": no tuning involved.
- `run_experiment.py`, `run_adaptive.py`, `run_lme.py`: `RESULTS_DIR` environment variable (default `results/`), so
  post-test runs write to `results/post_test/` and cannot overwrite locked outputs; `run_experiment.py` honours
  `default: false`.
- New: `src/make_locomo_adv_cases.py`, `data/locomo_adv_cases.json`, `run_locomo_adv.py` (see
  `docs/locomo_adv_comparison.md`), `src/pooled_analysis.py` (read-only), tests `tests/test_locomo_adv.py` and one
  new test in `tests/test_trust_gate.py`. 73 tests pass (laptop and server).

**Why the earlier results cannot change:** the default variant set and every existing branch of
`decide_candidate()` are byte-for-byte the same logic; the post-test runs re-use the LLM cache, and their
`no_defense` condition is recomputed from cache only to pair trials (pooled analysis keeps the original copy).

## 18 Nov 2026 — repository cleanup (non-functional)

**Removed** (still in git history): `src/hello_graph.py` (LangGraph warm-up exercise, never part of the experiment),
`src/run_week2.py` (no-defense runner, superseded by `run_experiment.py`; its numbers were never reported),
`data/adaptive_cases_v1.json` (AD3 v1, replaced on dev; see `docs/adaptive_attacks_spec.md`) and
`prompts/archive/gate_contradiction_v1.txt` (contradiction prompt v1, replaced on dev; see `docs/prompt_log.md`).
Local, git-ignored outputs of the fake model and of the two runs already marked invalid were deleted as well.
`docs/test_run_manifest.txt` still lists the two removed source files: it records the state at the test run.

**Code:** two unused imports removed (`re` in `src/textnorm.py`, `Path` in `src/tune_gate.py`), imports sorted in two
test files and `run_locomo_adv.py`, a few over-long lines wrapped in `src/time_sensitivity.py`,
`src/pooled_analysis.py` and `src/plots_adaptive.py`, one comment updated in `src/make_adaptive_attacks.py`.
Evidence: the AST of every edited file is identical to its previous version, apart from the removed or reordered
import statements; 73 tests pass.

**Docs:** `README.md` rewritten (all experiments, full layout, documentation index); status lines in
`docs/dataset2_plan.md` and `docs/adaptive_attacks_spec.md` brought up to date; RUNBOOK gained a section for the
additional experiments.
