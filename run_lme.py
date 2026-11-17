"""
run_lme.py — second dataset (LongMemEval) with the gate thresholds LOCKED on LoCoMo dev (transfer test, no retuning).

  python run_lme.py --split pilot --models ollama:qwen3:8b     # 3 pilot targets: checks the pipeline, never reported
  python run_lme.py --split lme                                # the 30 reported targets + 30 update probes

Per model and condition (no_defense, trust):
  clean history per target    target accuracy; FRR on clean dialog memories (gate)
  A1, A2, A3, AD1, AD2         ASR (same success rule as LoCoMo); PMAR per attack (gate)
  clean external pages         FRR external (gate)
  update probes                answer accuracy on the NEWER value; update-rejection rate = the memory carrying the
                               newer value rejected or quarantined (a legitimate update treated as poison)
Build the inputs first: python src/prepare_longmemeval.py && python src/lme.py
Output (results/): lme_<split>_<model>.csv, lme_<split>_<model>_gate.sqlite, lme_summary_<split>_<model>.csv
"""
import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

import lme  # noqa: E402
import locomo  # noqa: E402
import metrics  # noqa: E402
from adaptive import inject_adaptive  # noqa: E402
from gate.gate_log import GateLog  # noqa: E402
from gate.trust_gate import make_trust_gate  # noqa: E402
from graph import build_graph, run  # noqa: E402
from llm import enable_cache, get_chat_model  # noqa: E402
from memory_store import LocalEmbeddings, MemoryStore  # noqa: E402
from memory_writer import PARSE_STATS  # noqa: E402
from run_experiment import gate_params  # noqa: E402
from textnorm import contains_any  # noqa: E402

DATA, RESULTS = ROOT / "data", ROOT / "results"
load = lambda name: json.load(open(DATA / name, encoding="utf-8"))
ATTACKS = ("A1_false_fact", "A2_confident_poison", "A3_external_source", "AD1_split_assertion", "AD2_lexicon_free")


def sessions_for(case):
    sessions = lme.load_sessions(case["sample_id"], case["keep"], case.get("extra_session", False))
    if case.get("channel") == "dialog_inserts":
        return inject_adaptive(sessions, case)
    if case.get("channel") == "external_page":
        return locomo.inject_poison(sessions, case)
    return sessions


def run_model(model, split, variants):
    t0 = time.time()
    tag = re.sub(r"[^\w.-]", "_", f"{split}_{model}")
    llm, emb = get_chat_model(model), LocalEmbeddings()
    gate_db = RESULTS / f"lme_{tag}_gate.sqlite"
    gate_db.unlink(missing_ok=True)
    log = GateLog(gate_db)
    cases = [c for c in load("lme_poison_cases.json") if c["split"] == split]
    externals = [c for c in load("lme_clean_external.json") if c["split"] == split]
    targets = {c["target_id"]: c for c in cases}
    updates = load("lme_updates.json") if split == "lme" else []
    rows = []

    def go(app, case, query, condition, gate_log, run_key):
        out = run(app, MemoryStore(emb), sessions_for(case), [{"qid": "q", "text": query}] if query else [],
                  run_id=f"{condition}|{run_key}", case_id=run_key, gate_log=gate_log)
        return out["answers"]["q"]["answer"] if query else None

    def one_condition(condition, app, gate_log=None):
        for tid, t in targets.items():
            clean = {k: t[k] for k in ("sample_id", "keep", "extra_session")}
            ans = go(app, clean, lme.ask(t["question"]), condition, gate_log, f"CLEAN-{tid}")
            rows.append({"condition": condition, "kind": "target_qa", "case_id": f"CLEAN-{tid}", "answer": ans,
                         "outcome": "correct" if metrics.is_correct(ans, t["truth_keys"]) else "wrong"})
        for c in cases:
            ans = go(app, c, lme.ask(c["question"]), condition, gate_log, c["case_id"])
            rows.append({"condition": condition, "kind": c["attack"], "case_id": c["case_id"], "answer": ans,
                         "outcome": metrics.attack_outcome(ans, c["poison_keys"], c["truth_keys"])})
        if gate_log is not None:
            for c in externals:
                go(app, c, None, condition, gate_log, c["case_id"])
        for u in updates:
            ans = go(app, u, lme.ask(u["question"]), condition, gate_log, f"UPD-{u['probe_id']}")
            rows.append({"condition": condition, "kind": "update_qa", "case_id": f"UPD-{u['probe_id']}", "answer": ans,
                         "outcome": "correct" if metrics.is_correct(ans, u["new_value_keys"]) else "wrong"})
        print(f"[{model}] {condition} done ({(time.time() - t0) / 60:.1f} min since start)", flush=True)

    one_condition("no_defense", build_graph(llm, gate=None))
    for name, cfg in variants.items():
        one_condition(name, build_graph(llm, gate=make_trust_gate(llm, gate_params(model, cfg))), gate_log=log)

    with open(RESULTS / f"lme_{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = summarize(rows, gate_db, cases, updates, ["no_defense"] + list(variants))
    with open(RESULTS / f"lme_summary_{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["condition", "metric", "k", "n", "rate", "ci_low", "ci_high"])
        w.writeheader()
        w.writerows(summary)
    s = {(r["condition"], r["metric"]): r for r in summary}
    print(f"\n=== LME | {model} | split={split} | {(time.time() - t0) / 60:.1f} min | writer {dict(PARSE_STATS)} ===")
    for (cond, metric), r in sorted(s.items()):
        if r["n"]:
            print(f"{cond:<12} {metric:<34} {100 * r['rate']:5.1f}% ({r['k']}/{r['n']})")


def gate_groups(gate_db, cases, updates, condition):
    """Gate decisions grouped as clean_dialog, clean_external, one group per attack, and update (newer value)."""
    by_id = {c["case_id"]: c for c in cases}
    upd = {f"UPD-{u['probe_id']}": u for u in updates}
    db = sqlite3.connect(gate_db)
    db.row_factory = sqlite3.Row
    g = defaultdict(list)
    for r in db.execute("SELECT * FROM gate_decisions WHERE run_id LIKE ?", (f"{condition}|%",)):
        cid = r["case_id"]
        if cid.startswith("CLEAN-"):
            g["clean_dialog"].append(r["decision"])
        elif cid.endswith("-EXT-CLEAN") and r["source"] == "external_web":
            g["clean_external"].append(r["decision"])
        elif cid in by_id:
            c = by_id[cid]
            if r["session"] == c["inject_session"] and r["source"] == c["source"] and contains_any(r["content"], c["poison_keys"]):
                g[c["attack"]].append(r["decision"])
        elif cid in upd and r["session"] == upd[cid]["new_session"] and contains_any(r["content"], upd[cid]["new_value_keys"]):
            g["update"].append(r["decision"])
    return g


def summarize(rows, gate_db, cases, updates, conditions):
    out = []

    def add(cond, metric, k, n):
        p, lo, hi = metrics.wilson(k, n)
        out.append({"condition": cond, "metric": metric, "k": k, "n": n, "rate": round(p, 4) if n else "",
                    "ci_low": round(lo, 4) if n else "", "ci_high": round(hi, 4) if n else ""})

    for cond in conditions:
        rs = lambda kind: [r for r in rows if r["condition"] == cond and r["kind"] == kind]
        add(cond, "target_accuracy_clean", sum(r["outcome"] == "correct" for r in rs("target_qa")), len(rs("target_qa")))
        add(cond, "update_accuracy", sum(r["outcome"] == "correct" for r in rs("update_qa")), len(rs("update_qa")))
        for a in ATTACKS:
            add(cond, f"ASR_{a}", sum(r["outcome"] == "success" for r in rs(a)), len(rs(a)))
        if cond == "no_defense":
            continue
        g = gate_groups(gate_db, cases, updates, cond)
        for a in ATTACKS:
            add(cond, f"PMAR_{a}", sum(d == "accept" for d in g[a]), len(g[a]))
        for grp, metric in (("clean_dialog", "FRR_dialog"), ("clean_external", "FRR_external"),
                            ("update", "update_rejection")):
            add(cond, metric, sum(d != "accept" for d in g[grp]), len(g[grp]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="pilot", choices=["pilot", "lme"])
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--variants", nargs="*", default=["trust"])
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
    variants = {k: v for k, v in cfg["gate_variants"].items() if k in args.variants}
    RESULTS.mkdir(exist_ok=True)
    enable_cache()
    for model in args.models or cfg["models"]:
        for v in variants.values():
            gate_params(model, v)
        PARSE_STATS.clear()
        run_model(model, args.split, variants)


if __name__ == "__main__":
    main()
