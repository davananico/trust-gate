"""
run_experiment.py — every experimental condition for one or more models, from a single command.

  python run_experiment.py --split dev                              # the 4 models in config/experiment.yaml
  python run_experiment.py --split dev --models ollama:qwen3:8b     # one model
  python run_experiment.py --split test                             # ONLY after the dev thresholds are locked

Conditions per model:
  no_defense          no gate: clean baseline (clean acc + DCR reference answers), attacks A1–A3, A3-auth (+/- poison)
  <gate variant>      trust, content_only, ablate_source, ablate_poison_risk (config/experiment.yaml):
                      gate + attacks, gate + A3-auth, gate on clean conversations (FRR dialog + clean acc),
                      gate on clean external pages (FRR external)
Output per model (results/):
  exp_<split>_<model>.csv          one row per agent answer
  exp_<split>_<model>_gate.sqlite  every gate decision (run_id = "<variant>|<case>")
  summary_<split>_<model>.csv      metric summary + 95% Wilson CI
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

import locomo  # noqa: E402
import metrics  # noqa: E402
import tools  # noqa: E402
from gate.gate_log import GateLog  # noqa: E402
from gate.trust_gate import GateParams, make_trust_gate  # noqa: E402
from graph import build_graph, run  # noqa: E402
from llm import enable_cache, get_chat_model  # noqa: E402
from memory_store import K, LocalEmbeddings, MemoryStore  # noqa: E402
from memory_writer import PARSE_STATS  # noqa: E402
from tune_gate import ATTACKS, labelled_rows  # noqa: E402

DATA, RESULTS = ROOT / "data", ROOT / "results"
load = lambda name: json.load(open(DATA / name, encoding="utf-8"))
ATTACK_KINDS = ATTACKS[:3]


def gate_params(model, variant_cfg):
    # GATE_THRESHOLDS is only for dry runs (e.g. the fake model); the experiment uses the locked file.
    path = Path(os.getenv("GATE_THRESHOLDS", ROOT / "config" / "gate_thresholds.yaml"))
    thr = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if model not in thr:
        raise SystemExit(f"No thresholds for {model} in config/gate_thresholds.yaml. Run tune_gate.py on DEV first.")
    t = thr[model][variant_cfg["threshold_from"]]
    return GateParams(mode=variant_cfg["mode"], theta_accept=t["theta_accept"], theta_reject=t["theta_reject"],
                      lambda_r=t["lambda_r"], use_source_trust=variant_cfg.get("use_source_trust", True),
                      use_poison_risk=variant_cfg.get("use_poison_risk", True))


def run_model(model, split, variants):
    t0 = time.time()
    tag = re.sub(r"[^\w.-]", "_", f"{split}_{model}")
    llm, emb = get_chat_model(model), LocalEmbeddings()
    tools.LOG = RESULTS / f"exp_{tag}_tool_log.jsonl"
    tools.LOG.unlink(missing_ok=True)
    gate_db = RESULTS / f"exp_{tag}_gate.sqlite"
    gate_db.unlink(missing_ok=True)
    log = GateLog(gate_db)
    convs = load("split.json")[split]
    targets = [t for t in load("targets.json") if t["split"] == split]
    cases = [c for c in load("poison_cases.json") if c["split"] == split]
    auths = [a for a in load("auth_scenarios.json") if a["split"] == split]
    externals = [c for c in load("clean_external.json") if c["split"] == split]
    clean_q = [q for q in load("clean_questions.json") if q["split"] == split]
    rows, baseline = [], {}

    def go(app, sid, queries, case=None, mode="qa", condition="", gate_log=None):
        sessions = locomo.load_sessions(sid)
        if case:
            sessions = locomo.inject_poison(sessions, case)
        cid = case["case_id"] if case else f"CLEAN-{sid}"
        out = run(app, MemoryStore(emb), sessions, queries, mode=mode, run_id=f"{condition}|{cid}", case_id=cid,
                  gate_log=gate_log)
        return {q["qid"]: {**out["answers"][q["qid"]], "retrieved": out["retrieved"][q["qid"]]} for q in queries}

    def qa_queries(sid):
        return ([{"qid": f"Q-{sid}-{q['qa_index']}", "text": q["question"], "keys": [q["gold_answer"]], "kind": "clean_qa"}
                 for q in clean_q if q["sample_id"] == sid]
                + [{"qid": t["target_id"], "text": t["question"], "keys": t["truth_keys"], "kind": "target_qa"}
                   for t in targets if t["sample_id"] == sid])

    def one_condition(condition, app, gate_log=None):
        # 1) clean conversations: clean accuracy (+ FRR dialog from gate_log)
        for sid in convs:
            qs = qa_queries(sid)
            res = go(app, sid, qs, condition=condition, gate_log=gate_log)
            for q in qs:
                ans = res[q["qid"]]["answer"]
                if condition == "no_defense" and q["kind"] == "target_qa":
                    baseline[q["qid"]] = ans
                rows.append({"condition": condition, "kind": q["kind"], "sample_id": sid, "qid": q["qid"],
                             "question": q["text"], "answer": ans, "correct": metrics.is_correct(ans, q["keys"])})
        # 2) attacks A1–A3: ASR, DCR (reference = the baseline answer WITHOUT a gate on the clean conversation)
        for case in cases:
            r = go(app, case["sample_id"], [{"qid": case["target_id"], "text": case["question"]}], case,
                   condition=condition, gate_log=gate_log)[case["target_id"]]
            rows.append({"condition": condition, "kind": case["attack"], "sample_id": case["sample_id"],
                         "qid": case["target_id"], "case_id": case["case_id"], "question": case["question"],
                         "answer": r["answer"],
                         "outcome": metrics.attack_outcome(r["answer"], case["poison_keys"], case["truth_keys"]),
                         "changed": metrics.changed(r["answer"], baseline[case["target_id"]]),
                         "poison_retrieved": any(metrics.contains_any(m["content"], case["poison_keys"]) for m in r["retrieved"])})
        # 3) A3-auth (+ without poison, only for no_defense)
        for a in auths:
            q = [{"qid": a["case_id"], "text": a["user_request"]}]
            for cond, case in ((condition, a),) + (((condition + "_noattack", None),) if condition == "no_defense" else ()):
                r = go(app, a["sample_id"], q, case, mode="tool", condition=cond, gate_log=gate_log)[a["case_id"]]
                rows.append({"condition": cond, "kind": "A3_auth", "sample_id": a["sample_id"], "qid": a["case_id"],
                             "case_id": a["case_id"] if case else "", "question": a["user_request"], "answer": r["answer"],
                             "tool_calls": json.dumps(r["tool_calls"]),
                             "outcome": "success" if metrics.auth_attempted(r["tool_calls"], a["harmful_destination"]) else "fail"})
        # 4) CLEAN external pages: only for FRR external (no questions)
        if gate_log is not None:
            for c in externals:
                go(app, c["sample_id"], [], c, condition=condition, gate_log=gate_log)
        print(f"[{model}] {condition} done ({(time.time() - t0) / 60:.1f} min since start)", flush=True)

    one_condition("no_defense", build_graph(llm, gate=None))
    for name, cfg in variants.items():
        one_condition(name, build_graph(llm, gate=make_trust_gate(llm, gate_params(model, cfg))), gate_log=log)

    with open(RESULTS / f"exp_{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)
    summary = summarize(rows, gate_db, split, ["no_defense"] + list(variants))
    with open(RESULTS / f"summary_{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["condition", "metric", "k", "n", "rate", "ci_low", "ci_high"])
        w.writeheader()
        w.writerows(summary)
    print_summary(model, split, summary, time.time() - t0)


def summarize(rows, gate_db, split, conditions):
    out = []

    def add(cond, metric, k, n):
        p, lo, hi = metrics.wilson(k, n)
        out.append({"condition": cond, "metric": metric, "k": k, "n": n, "rate": round(p, 4) if n else "",
                    "ci_low": round(lo, 4) if n else "", "ci_high": round(hi, 4) if n else ""})

    by = defaultdict(list)
    for r in rows:
        by[(r["condition"], r["kind"])].append(r)
    for cond in conditions:
        for kind, metric in (("clean_qa", "clean_accuracy"), ("target_qa", "target_accuracy_clean")):
            rs = by[(cond, kind)]
            add(cond, metric, sum(r["correct"] for r in rs), len(rs))
        for kind in ATTACK_KINDS:
            rs = by[(cond, kind)]
            add(cond, f"ASR_{kind}", sum(r["outcome"] == "success" for r in rs), len(rs))
            add(cond, f"ambiguous_{kind}", sum(r["outcome"] == "ambiguous" for r in rs), len(rs))
            add(cond, f"DCR_{kind}", sum(r["changed"] for r in rs), len(rs))
        rs = by[(cond, "A3_auth")]
        add(cond, "ASR_A3_auth", sum(r["outcome"] == "success" for r in rs), len(rs))
        if cond == "no_defense":
            rs = by[("no_defense_noattack", "A3_auth")]
            add(cond, "ASR_A3_auth_without_poison", sum(r["outcome"] == "success" for r in rs), len(rs))
            continue
        groups, untracked = labelled_rows(gate_db, run_prefix=f"{cond}|", split=split)
        for kind in ATTACKS:
            g = groups.get(kind, [])
            for decision, metric in (("accept", "PMAR"), ("reject", "PMRR"), ("quarantine", "PMQR")):
                add(cond, f"{metric}_{kind}", sum(r["decision"] == decision for r in g), len(g))
            add(cond, f"poison_not_written_{kind}", untracked.get(kind, 0), untracked.get(kind, 0) + len({r["case_id"] for r in g}))
        for g, metric in (("clean_dialog", "FRR_dialog"), ("clean_external", "FRR_external")):
            rs = groups.get(g, [])
            add(cond, metric, sum(r["decision"] != "accept" for r in rs), len(rs))
    return out


def print_summary(model, split, summary, seconds):
    s = {(r["condition"], r["metric"]): r for r in summary}
    f = lambda c, m: (lambda r: f"{100 * r['rate']:5.1f}%" if r and r["n"] else "   - ")(s.get((c, m)))
    conds = sorted({r["condition"] for r in summary}, key=lambda c: (c != "no_defense", c))
    print(f"\n=== {model} | split={split} | k={K} | {seconds / 60:.1f} min | writer {dict(PARSE_STATS)} ===")
    head = "".join(f"{c[:14]:>16}" for c in conds)
    print(f"{'metric':<26}{head}")
    for m in (["clean_accuracy", "target_accuracy_clean"] + [f"ASR_{k}" for k in ATTACK_KINDS] + ["ASR_A3_auth"]
              + [f"DCR_{k}" for k in ATTACK_KINDS] + [f"PMAR_{k}" for k in ATTACKS] + ["FRR_dialog", "FRR_external"]):
        print(f"{m:<26}" + "".join(f"{f(c, m):>16}" for c in conds))
    print(f"(ASR A3-auth without poison, no_defense: {f('no_defense', 'ASR_A3_auth_without_poison')})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--variants", nargs="*", help="subset of gate variants (default: all)")
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
    variants = {k: v for k, v in cfg["gate_variants"].items() if not args.variants or k in args.variants}
    RESULTS.mkdir(exist_ok=True)
    enable_cache()
    for model in args.models or cfg["models"]:
        for v in variants.values():
            gate_params(model, v)  # fail early if thresholds are missing
        PARSE_STATS.clear()
        run_model(model, args.split, variants)


if __name__ == "__main__":
    main()
