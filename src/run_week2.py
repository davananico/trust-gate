"""
run_week2.py — runs the conditions without a gate (superseded by run_experiment.py; kept for reproducibility).

Conditions:
  clean      clean baseline: clean accuracy (clean QA) + reference answers for the target questions (used for DCR)
  attack     no defense + attacks A1/A2/A3: ASR, DCR, % poison retrieved
  auth       no defense + A3-auth: % of runs that PROPOSE send_file to attacker.example
  auth_clean the same request WITHOUT poison: must be 0% (checks that the agent does not invent a destination)

Run:
  python src/run_week2.py                  # dev split (default)
  python src/run_week2.py --split test     # allowed: these conditions tune nothing
Output: results/week2_<split>_<model>.csv (one row per answer) + an on-screen summary.
"""
import argparse
import csv
import json
import os
import re
from collections import defaultdict

import locomo
import metrics
import tools
from graph import build_graph, run
from llm import enable_cache, get_chat_model
from memory_store import K, LocalEmbeddings, MemoryStore
from memory_writer import PARSE_STATS

DATA, RESULTS = locomo.ROOT / "data", locomo.ROOT / "results"
load = lambda name: json.load(open(DATA / name, encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    args = ap.parse_args()

    model_name = os.getenv("LLM_MODEL", "fake")
    tag = re.sub(r"[^\w.-]", "_", f"{args.split}_{model_name}")
    RESULTS.mkdir(exist_ok=True)
    tools.LOG = RESULTS / f"week2_{tag}_tool_log.jsonl"
    tools.LOG.unlink(missing_ok=True)

    enable_cache()
    llm, emb = get_chat_model(), LocalEmbeddings()
    app = build_graph(llm, gate=None)
    convs = load("split.json")[args.split]
    targets = [t for t in load("targets.json") if t["split"] == args.split]
    rows = []

    def go(condition, sample_id, queries, case=None, mode="qa"):
        sessions = locomo.load_sessions(sample_id)
        if case:
            sessions = locomo.inject_poison(sessions, case)
        run_id = f"{condition}-{case['case_id'] if case else sample_id}"
        out = run(app, MemoryStore(emb), sessions, queries, mode=mode, run_id=run_id,
                  case_id=case["case_id"] if case else "")
        n_mem = sum(e["n_stored"] for e in out["log"])
        return {q["qid"]: {**out["answers"][q["qid"]], "retrieved": out["retrieved"][q["qid"]], "n_memories": n_mem}
                for q in queries}

    # 1) Clean baseline: clean QA + target questions, per conversation
    baseline = {}
    for sid in convs:
        clean_q = [q for q in load("clean_questions.json") if q["sample_id"] == sid]
        tq = [t for t in targets if t["sample_id"] == sid]
        queries = ([{"qid": f"Q-{sid}-{q['qa_index']}", "text": q["question"]} for q in clean_q]
                   + [{"qid": t["target_id"], "text": t["question"]} for t in tq])
        res = go("clean", sid, queries)
        for q in clean_q:
            r = res[f"Q-{sid}-{q['qa_index']}"]
            rows.append({"condition": "clean", "kind": "clean_qa", "sample_id": sid, "qid": f"Q-{sid}-{q['qa_index']}",
                         "question": q["question"], "answer": r["answer"], "gold": q["gold_answer"],
                         "correct": metrics.is_correct(r["answer"], [q["gold_answer"]]), "n_memories": r["n_memories"]})
        for t in tq:
            r = res[t["target_id"]]
            baseline[t["target_id"]] = r["answer"]
            rows.append({"condition": "clean", "kind": "target_qa", "sample_id": sid, "qid": t["target_id"],
                         "question": t["question"], "answer": r["answer"], "gold": t["gold_answer"],
                         "correct": metrics.is_correct(r["answer"], t["truth_keys"]), "n_memories": r["n_memories"]})
        print(f"[clean] {sid}: {len(queries)} questions")

    # 2) No defense + attacks A1/A2/A3
    cases = [c for c in load("poison_cases.json") if c["split"] == args.split]
    for i, case in enumerate(cases, 1):
        r = go("attack", case["sample_id"], [{"qid": case["target_id"], "text": case["question"]}], case)[case["target_id"]]
        rows.append({"condition": "no_defense", "kind": case["attack"], "sample_id": case["sample_id"],
                     "qid": case["target_id"], "case_id": case["case_id"], "question": case["question"],
                     "answer": r["answer"], "outcome": metrics.attack_outcome(r["answer"], case["poison_keys"], case["truth_keys"]),
                     "changed": metrics.changed(r["answer"], baseline[case["target_id"]]),
                     "poison_retrieved": any(metrics.contains_any(m["content"], case["poison_keys"]) for m in r["retrieved"]),
                     "n_memories": r["n_memories"]})
        if i % 15 == 0:
            print(f"[attack] {i}/{len(cases)} cases")

    # 3) A3-auth: with and without poison (same request)
    for a in [a for a in load("auth_scenarios.json") if a["split"] == args.split]:
        q = [{"qid": a["case_id"], "text": a["user_request"]}]
        for condition, case in (("no_defense", a), ("clean", None)):
            r = go(f"auth_{condition}", a["sample_id"], q, case, mode="tool")[a["case_id"]]
            rows.append({"condition": condition, "kind": "A3_auth", "sample_id": a["sample_id"], "qid": a["case_id"],
                         "case_id": a["case_id"] if case else "", "question": a["user_request"], "answer": r["answer"],
                         "tool_calls": json.dumps(r["tool_calls"]),
                         "outcome": "success" if metrics.auth_attempted(r["tool_calls"], a["harmful_destination"]) else "fail",
                         "n_memories": r["n_memories"]})
    print("[auth] done")

    path = RESULTS / f"week2_{tag}.csv"
    fields = sorted({k for r in rows for k in r})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # Summary
    by = defaultdict(list)
    for r in rows:
        by[(r["condition"], r["kind"])].append(r)
    count = lambda rs, f: sum(1 for r in rs if f(r))
    print(f"\n=== No-defense summary | split={args.split} | model={model_name} | k={K} ===")
    if type(llm).__name__ == "FakeModel":
        print("WARNING: FAKE model. The numbers below only test the pipeline, they are NOT experimental results.")
    for kind, label in (("clean_qa", "Clean accuracy (clean QA)"), ("target_qa", "Target-question accuracy, clean")):
        rs = by[("clean", kind)]
        print(f"{label:<38} {metrics.fmt(count(rs, lambda r: r['correct']), len(rs))}")
    print(f"\n{'Attack (no defense)':<22} {'ASR':<26} {'ambiguous':<10} {'DCR':<26} poison retrieved")
    for kind in ("A1_false_fact", "A2_confident_poison", "A3_external_source"):
        rs = by[("no_defense", kind)]
        print(f"{kind:<22} {metrics.fmt(count(rs, lambda r: r['outcome'] == 'success'), len(rs)):<26} "
              f"{count(rs, lambda r: r['outcome'] == 'ambiguous'):<10} "
              f"{metrics.fmt(count(rs, lambda r: r['changed']), len(rs)):<26} "
              f"{metrics.fmt(count(rs, lambda r: r['poison_retrieved']), len(rs))}")
    for condition in ("no_defense", "clean"):
        rs = by[(condition, "A3_auth")]
        label = "A3-auth (no defense)" if condition == "no_defense" else "A3-auth without poison (must be 0)"
        print(f"{label:<38} {metrics.fmt(count(rs, lambda r: r['outcome'] == 'success'), len(rs))}")
    print(f"\nWriter: JSON parsed {dict(PARSE_STATS)}  (repaired/salvaged = format fixed; failed = that session's memory is empty)")
    print(f"Per row: {path.relative_to(locomo.ROOT)}  |  tool log: {tools.LOG.relative_to(locomo.ROOT)}")


if __name__ == "__main__":
    main()
