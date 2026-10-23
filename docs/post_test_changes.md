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
