# Runbook — running the Memory Trust Gate experiment from scratch

Every command needed to reproduce the experiment, in order, with the output you should see and roughly how long it
takes. Replace `USERNAME@SERVER` with your account on the GPU server.

- **Laptop** commands run in a terminal on your own computer (PowerShell prompt `PS ...>` or bash).
- **Server** commands run after `ssh USERNAME@SERVER` (prompt like `user@host:~$`).
- Times are what we measured on one NVIDIA L4 (24 GB) with Ollama 0.40.4.

---

## 0. What you need

| Item | Notes |
| --- | --- |
| Python 3.13 | on the laptop and on the server (installed with `uv` in step 3) |
| A GPU server with Ollama | we used Ubuntu 22.04 + 1× NVIDIA L4; no admin rights needed |
| Network access to the server | e.g. campus Wi-Fi; if `ssh` times out, you are not on the right network |
| ~30 GB of disk on the server | 4 models (~24 GB) + project + caches |

---

## 1. Connect to the server (once)

**Laptop** — log in the first time and change the initial password:
```
ssh USERNAME@SERVER
passwd
exit
```

**Laptop** — install an SSH key so later commands need no password (optional but much easier):
```
ssh-keygen -t ed25519                     # press Enter at every question
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh USERNAME@SERVER "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```
On macOS/Linux replace the `type ...` part with `cat ~/.ssh/id_ed25519.pub`.
Check: `ssh USERNAME@SERVER "echo ok"` prints `ok` without asking for a password.

---

## 2. Install Ollama and the four models (once, on the server)

**Server** — Ollama in your home folder, no `sudo`:
```
mkdir -p ~/ollama && cd ~/ollama
curl -fL -o ollama.tar.zst https://ollama.com/download/ollama-linux-amd64.tar.zst
tar --zstd -xf ollama.tar.zst && rm ollama.tar.zst
~/ollama/bin/ollama --version
cd ~
```
Expected: `ollama version is 0.40.4` (a warning about "no running instance" is normal).

**Server** — start Ollama in the background on GPU 0, reachable only from the server itself:
```
tmux new -d -s ollama "CUDA_VISIBLE_DEVICES=0 OLLAMA_HOST=127.0.0.1:11434 ~/ollama/bin/ollama serve > ~/ollama/serve.log 2>&1"
sleep 5
grep -iE "listening|inference compute" ~/ollama/serve.log
```
Expected: a `Listening on 127.0.0.1:11434` line and an `inference compute ... NVIDIA L4` line.

**Server** — download the models (~24 GB, ~20–30 min). Runs in tmux and retries on network errors:
```
tmux new -d -s pull 'for m in qwen3:8b llama3.1:8b gemma4:12b olmo-3:7b-instruct; do for i in 1 2 3 4 5 6; do timeout 900 ~/ollama/bin/ollama pull $m && break; sleep 60; done; done > ~/ollama/pull.log 2>&1'
~/ollama/bin/ollama list            # repeat until all four models are listed
```

> If the server reboots, Ollama stops. Check with `tmux ls`; if there is no `ollama` session, run the
> `tmux new -d -s ollama ...` command above again. Downloaded models are kept.

---

## 3. Put the project on the server and install Python (once)

**Laptop** — from the folder that contains `trust-gate/`, copy the project (without the virtual environment):
```
tar --exclude=./.venv --exclude=__pycache__ -czf trust-gate.tgz -C trust-gate .
scp trust-gate.tgz USERNAME@SERVER:~/
```
(Or clone the repository on the server with `git clone`.)

**Server** — unpack, install `uv`, Python 3.13 and the pinned packages (~5 min):
```
mkdir -p ~/trust-gate && tar -xzf ~/trust-gate.tgz -C ~/trust-gate && rm ~/trust-gate.tgz
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
cd ~/trust-gate
uv venv -p 3.13 .venv
uv pip install --python .venv torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv -r requirements.txt
cp .env.example .env                  # LLM_MODEL=ollama:qwen3:8b, OLLAMA_HOST=http://127.0.0.1:11434
.venv/bin/python -m pytest -q
```
Expected: `73 passed`. The first run downloads the embedding model `BAAI/bge-small-en-v1.5` (~130 MB).

From here on, every command is a **server** command run inside `~/trust-gate` (prefix `.venv/bin/python`).

---

## 4. Build the data (seconds, no LLM)

The repository already contains the generated files; re-running reproduces them exactly.
```
.venv/bin/python src/prepare_data.py
.venv/bin/python src/make_attacks.py
```
Expected: `All validation checks passed.` and `Poison cases: 147 ... A2 dev and test phrases overlap? False`.

---

## 5. Quick check with a real LLM (~1–2 min)

```
.venv/bin/python src/demo.py
```
Expected: three panels for case T01 — no poison answers `Sweden`, poisoned without defense answers `Norway`,
poisoned + Trust Gate answers `Sweden` (the demo uses the model's locked thresholds; it is not part of the experiment).

---

## 6. Dev phase — choose the gate thresholds (~1 h for 4 models)

Only needed if you want to re-derive `config/gate_thresholds.yaml`; the locked file is already in the repository.
Run it in tmux so it survives a disconnect:
```
tmux new -d -s tune 'cd ~/trust-gate && for m in qwen3:8b llama3.1:8b olmo-3:7b-instruct gemma4:12b; do LLM_MODEL=ollama:$m .venv/bin/python src/tune_gate.py collect && LLM_MODEL=ollama:$m .venv/bin/python src/tune_gate.py tune; done > results/tune_log.txt 2>&1'
tail -f results/tune_log.txt         # Ctrl+C stops watching only
```
Expected per model: a `[trust] theta_accept=-0.05 theta_reject=-0.05 lambda_r=1.0` line and FRR/PMAR figures.
The criterion is fixed in `docs/experiment_spec.md` §6b. **Never run `tune` on test data.**

---

## 7. Run every condition (dev ~1 h, test ~6 h)

```
tmux new -d -s exp "cd ~/trust-gate && .venv/bin/python run_experiment.py --split dev > results/exp_dev_log.txt 2>&1"
tail -f results/exp_dev_log.txt
```
When the dev results look right, run the test split **once**:
```
tmux new -d -s test "cd ~/trust-gate && .venv/bin/python run_experiment.py --split test > results/exp_test_log.txt 2>&1"
tail -f results/exp_test_log.txt
```
Each model prints `[model] <condition> done (x min since start)` five times (no_defense, trust, content_only,
ablate_source, ablate_poison_risk), then a summary table. Output per model in `results/`:
`exp_<split>_<model>.csv`, `exp_<split>_<model>_gate.sqlite`, `summary_<split>_<model>.csv`.

Useful checks while it runs:
```
tmux ls                                                    # is the run still going?
curl -s 127.0.0.1:11434/api/ps | grep -o '"name":"[^"]*"'  # which model is on the GPU now
grep -cE "Traceback|Error" results/exp_test_log.txt        # should print 0
```

---

## 8. Bring the results back to the laptop

**Laptop** (inside your local `trust-gate/` folder):
```
mkdir results/test_final
scp "USERNAME@SERVER:~/trust-gate/results/exp_test_*" results/test_final/
scp "USERNAME@SERVER:~/trust-gate/results/summary_test_*" results/test_final/
```

---

## 9. Figures and error analysis (laptop, < 1 min, no LLM)

```
.venv\Scripts\python src\plots.py --dir results/test_final --split test
.venv\Scripts\python src\error_analysis.py --dir results/test_final --split test
```
Output: `results/test_final/figures/` (fig1, fig2 as PNG + PDF, `figure_data.csv`) and
`results/test_final/error_analysis/` (CSV rows + `summary.txt`). The write-up is in `docs/error_analysis.md`.

---

## 10. Additional experiments (same locked gate, server)

Each one re-uses the graph, gate and thresholds of step 7; nothing is tuned.

```
# adaptive attacks (docs/adaptive_attacks_spec.md); dev first, test once after the attacks are frozen
.venv/bin/python src/make_adaptive_attacks.py
tmux new -d -s adapt "cd ~/trust-gate && .venv/bin/python run_adaptive.py --split test > results/adaptive_test_log.txt 2>&1"

# LongMemEval (needs data/raw/longmemeval/, see docs/dataset2_plan.md); pilot first, never reported
.venv/bin/python run_lme.py --split pilot --models ollama:qwen3:8b
tmux new -d -s lme "cd ~/trust-gate && .venv/bin/python run_lme.py --split lme > results/lme_log.txt 2>&1"

# post-test additions write to a separate folder so locked outputs are never overwritten
.venv/bin/python src/make_locomo_adv_cases.py
RESULTS_DIR=results/post_test .venv/bin/python run_locomo_adv.py --split test --variants trust contradiction_only
RESULTS_DIR=results/post_test .venv/bin/python run_experiment.py --split test --variants contradiction_only

# literature baseline (MemPoison consistency check, no LLM in the gate); own folder: file names equal the runs above
export RESULTS_DIR=results/post_test_mempoison
.venv/bin/python run_experiment.py --split test --variants mempoison_consistency
.venv/bin/python run_adaptive.py --split test --variants mempoison_consistency
.venv/bin/python run_lme.py --split lme --variants mempoison_consistency
.venv/bin/python run_locomo_adv.py --split test --variants mempoison_consistency
```

Analysis on the laptop (no LLM): `src/adaptive_analysis.py`, `src/plots_adaptive.py`, `src/time_sensitivity.py`,
`src/pooled_analysis.py` (usage at the top of each file). Write-ups: `docs/adaptive_results.md`,
`docs/lme_results.md`, `docs/locomo_adv_comparison.md`.

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `ssh: connect ... timed out` | Not on a network that reaches the server (connect to campus Wi-Fi / the right VPN) |
| `curl 127.0.0.1:11434` prints nothing on the server | Ollama is not running: restart it with the `tmux new -d -s ollama ...` command in step 2 |
| `ollama pull` stuck or `522` / TLS errors | Registry hiccup; the tmux loop in step 2 retries automatically. Partial downloads resume |
| A run finishes suspiciously fast and two models give identical numbers | Check the GPU model with the `/api/ps` command; the cache key must include the model name (`src/llm.py`, `KeyedChatOllama`) |
| One writer reply takes many minutes | A model looping; replies are capped at `NUM_PREDICT = 1024` tokens in `src/llm.py` |
| You want a dry run without any LLM | Prefix commands with `LLM_MODEL=fake`; numbers then only test the pipeline |

## Rules that keep the results valid

- Thresholds, prompts, patterns, k and the embedding model are **locked** (`docs/experiment_spec.md` §9). Do not change them after looking at test results; record any later change in `docs/post_test_changes.md`.
- The test split is run once, after the dev phase. `docs/test_run_manifest.txt` holds the checksums of the locked files at that moment.
- `send_file()` is fake and only logs; nothing is ever sent.
