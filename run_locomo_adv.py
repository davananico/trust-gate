"""
run_locomo_adv.py — LoCoMo-Adv text attacks (data/locomo_adv_cases.json) against no defense and the locked gates.

Added after the test run (18 Nov 2026) as an external comparison point; gate, thresholds and prompts unchanged.
Build the cases first: python src/make_locomo_adv_cases.py

Run (server):
  RESULTS_DIR=results/post_test python run_locomo_adv.py --split test --variants trust contradiction_only

Per attack family:
  target_accuracy  agent still gives the true answer to the target question under attack (all families)
  ASR              agent gives the poison value (LA_fact_overwrite only: the other families state no false value)
  PMAR             attack memories accepted by the gate. Attack memories = every candidate from an external page in
                   the run (clean LoCoMo conversations have no external pages, so all of them come from the attack)
  attack_written   cases where the writer produced at least one memory from the attack page(s)
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

import locomo  # noqa: E402
import metrics  # noqa: E402
from gate.gate_log import GateLog  # noqa: E402
from gate.trust_gate import make_trust_gate  # noqa: E402
from graph import build_graph, run  # noqa: E402
from llm import enable_cache, get_chat_model  # noqa: E402
from make_locomo_adv_cases import FAMILIES, inject_pages  # noqa: E402
from memory_store import LocalEmbeddings, MemoryStore  # noqa: E402
from memory_writer import PARSE_STATS  # noqa: E402
from run_experiment import gate_params  # noqa: E402

DATA, RESULTS = ROOT / "data", Path(os.getenv("RESULTS_DIR", ROOT / "results"))


def run_model(model, split, variants, cases):
    t0 = time.time()
    tag = re.sub(r"[^\w.-]", "_", f"{split}_{model}")
    llm, emb = get_chat_model(model), LocalEmbeddings()
    gate_db = RESULTS / f"locomo_adv_{tag}_gate.sqlite"
    gate_db.unlink(missing_ok=True)
    log = GateLog(gate_db)
    rows = []

    def one_condition(condition, app, gate_log=None):
        for case in cases:
            sessions = inject_pages(locomo.load_sessions(case["sample_id"]), case)
            q = [{"qid": case["target_id"], "text": case["question"]}]
            out = run(app, MemoryStore(emb), sessions, q, run_id=f"{condition}|{case['case_id']}",
                      case_id=case["case_id"], gate_log=gate_log)
            ans = out["answers"][case["target_id"]]["answer"]
            rows.append({"condition": condition, "attack": case["attack"], "case_id": case["case_id"],
                         "sample_id": case["sample_id"], "question": case["question"], "answer": ans,
                         "correct": metrics.is_correct(ans, case["truth_keys"]),
                         "outcome": metrics.attack_outcome(ans, case["poison_keys"], case["truth_keys"])
                         if case["poison_keys"] else "",
                         "attack_retrieved": any(m["source"] == "external_web"
                                                 for m in out["retrieved"][case["target_id"]])})
        print(f"[{model}] {condition} done ({(time.time() - t0) / 60:.1f} min since start)", flush=True)

    one_condition("no_defense", build_graph(llm, gate=None))
    for name, cfg in variants.items():
        one_condition(name, build_graph(llm, gate=make_trust_gate(llm, gate_params(model, cfg))), gate_log=log)

    with open(RESULTS / f"locomo_adv_{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = summarize(rows, gate_db, cases, ["no_defense"] + list(variants))
    with open(RESULTS / f"locomo_adv_summary_{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["condition", "metric", "k", "n", "rate", "ci_low", "ci_high"])
        w.writeheader()
        w.writerows(summary)
    print_summary(model, split, summary, time.time() - t0)


def attack_decisions(gate_db, condition):
    """Gate decisions on candidates from the injected external pages, per case_id."""
    db = sqlite3.connect(gate_db)
    out = defaultdict(list)
    for cid, decision in db.execute("SELECT case_id, decision FROM gate_decisions WHERE run_id LIKE ? "
                                    "AND source = 'external_web'", (f"{condition}|%",)):
        out[cid].append(decision)
    return out


def summarize(rows, gate_db, cases, conditions):
    out = []

    def add(cond, metric, k, n):
        p, lo, hi = metrics.wilson(k, n)
        out.append({"condition": cond, "metric": metric, "k": k, "n": n, "rate": round(p, 4) if n else "",
                    "ci_low": round(lo, 4) if n else "", "ci_high": round(hi, 4) if n else ""})

    for cond in conditions:
        dec = attack_decisions(gate_db, cond) if cond != "no_defense" else {}
        for fam in FAMILIES + ("ALL",):
            rs = [r for r in rows if r["condition"] == cond and (fam == "ALL" or r["attack"] == fam)]
            add(cond, f"target_accuracy_{fam}", sum(r["correct"] for r in rs), len(rs))
            if fam == "LA_fact_overwrite":
                add(cond, f"ASR_{fam}", sum(r["outcome"] == "success" for r in rs), len(rs))
                add(cond, f"ambiguous_{fam}", sum(r["outcome"] == "ambiguous" for r in rs), len(rs))
            if cond == "no_defense":
                continue
            ids = [c["case_id"] for c in cases if fam == "ALL" or c["attack"] == fam]
            ds = [d for cid in ids for d in dec.get(cid, [])]
            for decision, metric in (("accept", "PMAR"), ("reject", "PMRR"), ("quarantine", "PMQR")):
                add(cond, f"{metric}_{fam}", sum(d == decision for d in ds), len(ds))
            add(cond, f"attack_written_{fam}", sum(cid in dec for cid in ids), len(ids))
    return out


def print_summary(model, split, summary, seconds):
    s = {(r["condition"], r["metric"]): r for r in summary}
    f = lambda c, m: (lambda r: f"{100 * r['rate']:5.1f}% ({r['k']}/{r['n']})" if r and r["n"] else "   -")(s.get((c, m)))
    conds = sorted({r["condition"] for r in summary}, key=lambda c: (c != "no_defense", c))
    print(f"\n=== LOCOMO-ADV | {model} | split={split} | {seconds / 60:.1f} min | writer {dict(PARSE_STATS)} ===")
    print(f"{'metric':<42}" + "".join(f"{c[:18]:>22}" for c in conds))
    fams = FAMILIES + ("ALL",)
    for m in ([f"target_accuracy_{a}" for a in fams] + ["ASR_LA_fact_overwrite"] + [f"PMAR_{a}" for a in fams]
              + [f"attack_written_{a}" for a in fams]):
        print(f"{m:<42}" + "".join(f"{f(c, m):>22}" for c in conds))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--variants", nargs="*", default=["trust", "contradiction_only"])
    ap.add_argument("--limit", type=int, help="first N cases only (dry runs)")
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
    variants = {k: v for k, v in cfg["gate_variants"].items() if k in args.variants}
    cases = [c for c in json.load(open(DATA / "locomo_adv_cases.json", encoding="utf-8")) if c["split"] == args.split]
    cases = cases[:args.limit] if args.limit else cases
    RESULTS.mkdir(parents=True, exist_ok=True)
    enable_cache()
    for model in args.models or cfg["models"]:
        for v in variants.values():
            gate_params(model, v)  # fail early if thresholds are missing
        PARSE_STATS.clear()
        run_model(model, args.split, variants, cases)


if __name__ == "__main__":
    main()
