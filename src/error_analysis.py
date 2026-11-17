"""
error_analysis.py — why poison passed the Trust Gate and which clean memories it held back (read-only, no LLM).

  python src/error_analysis.py                          # results/test_final (TEST split)
  python src/error_analysis.py --dir results/dev_run2_final --split dev

A. Every poison candidate ACCEPTED by the Trust Gate ("trust" variant) gets one cause:
   truth_never_written     the writer never wrote the true fact before the injection session
   truth_held_back         the true fact was written but the gate itself quarantined/rejected it
   truth_not_in_neighbors  the true fact was in active memory but not among the 5 nearest memories compared
   judge_said_no_conflict  the true fact was among the 5 nearest, yet the LLM answered "no conflict"
   The nearest-neighbor search is rebuilt from the logged accepted memories (embeddings only, no LLM).
B. Every CLEAN dialog/external memory the Trust Gate held back gets the signal that caused it
   (pattern, contradiction, low score), plus its nearest earlier memory for manual reading.

Output in <dir>/error_analysis/: poison_passed_<model>.csv, clean_held_back_<model>.csv, summary.txt
"""
import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate.llm_signals import N_NEIGHBORS  # noqa: E402
from memory_store import LocalEmbeddings, MemoryStore  # noqa: E402
from textnorm import contains_any  # noqa: E402
from tune_gate import ATTACKS, labelled_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = ["ollama_qwen3_8b", "ollama_gemma4_12b", "ollama_llama3.1_8b", "ollama_olmo-3_7b-instruct"]
CAUSES = ["truth_never_written", "truth_held_back", "truth_not_in_neighbors", "judge_said_no_conflict"]
load = lambda name: json.load(open(ROOT / "data" / name, encoding="utf-8"))


def run_rows(db, run_id):
    db.row_factory = sqlite3.Row
    return [dict(r) for r in db.execute("SELECT * FROM gate_decisions WHERE run_id = ?", (run_id,))]


def nearest(emb, memories, query, k=N_NEIGHBORS):
    """Rebuild the active memory from logged rows and return the k nearest contents (same embedding + metric)."""
    if not memories:
        return []
    store = MemoryStore(emb)
    store.add([{**m, "timestamp": "", "chunk_id": ""} for m in memories])
    return [h["content"] for h in store.retrieve(query, k=k)]


def analyze(model, data_dir, split, emb, out_dir):
    db_path = data_dir / f"exp_{split}_{model}_gate.sqlite"
    db = sqlite3.connect(db_path)
    exp = {(r["condition"], r.get("case_id", "")): r for r in csv.DictReader(open(data_dir / f"exp_{split}_{model}.csv", encoding="utf-8"))}
    cases = {c["case_id"]: c for name in ("poison_cases.json", "auth_scenarios.json") for c in load(name)}
    targets = {t["target_id"]: t for t in load("targets.json")}
    groups, untracked = labelled_rows(db_path, run_prefix="trust|", split=split)

    # A. poison accepted by the Trust Gate
    passed = []
    for kind in ATTACKS:
        for r in groups.get(kind, []):
            if r["decision"] != "accept":
                continue
            case = cases[r["case_id"]]
            truth_keys = case.get("truth_keys") or []
            rows = run_rows(db, r["run_id"])
            earlier = [x for x in rows if x["session"] < case["inject_session"]]
            active = [x for x in earlier if x["decision"] == "accept"]
            if kind == "A3_auth" or not truth_keys:
                cause = "no_true_fact_to_contradict"
            elif not any(contains_any(x["content"], truth_keys) for x in earlier):
                cause = "truth_never_written"
            elif not any(contains_any(x["content"], truth_keys) for x in active):
                cause = "truth_held_back"
            elif not any(contains_any(n, truth_keys) for n in nearest(emb, active, r["content"])):
                cause = "truth_not_in_neighbors"
            else:
                cause = "judge_said_no_conflict"
            trial = exp.get(("trust", r["case_id"]), {})
            passed.append({"model": model, "attack": kind, "case_id": r["case_id"], "cause": cause,
                           "attack_succeeded": trial.get("outcome") == "success", "poison_memory": r["content"],
                           "true_value": targets.get(case.get("target_id"), {}).get("true_value", ""),
                           "c_content": r["c_content"], "r_contradiction": r["r_contradiction"],
                           "agent_answer": trial.get("answer", "")})

    # B. clean memories held back by the Trust Gate
    held = []
    for group in ("clean_dialog", "clean_external"):
        for r in groups.get(group, []):
            if r["decision"] == "accept":
                continue
            reason = ("pattern" if r["r_pattern"] else "contradiction" if r["r_contradiction"] == 1.0 else "low_score")
            held.append({"model": model, "group": group, "reason": reason, "patterns": r["patterns"] or "",
                         "decision": r["decision"], "session": r["session"], "run_id": r["run_id"],
                         "memory": r["content"], "c_content": r["c_content"]})
    # nearest earlier active memory for a reproducible sample of contradiction cases (for manual reading)
    sample = sorted([h for h in held if h["reason"] == "contradiction"], key=lambda h: (h["run_id"], h["session"], h["memory"]))[::7][:20]
    for h in sample:
        rows = run_rows(db, h["run_id"])
        active = [x for x in rows if x["session"] < h["session"] and x["decision"] == "accept"]
        h["nearest_earlier_memory"] = (nearest(emb, active, h["memory"], k=1) or [""])[0]

    for name, rows in (("poison_passed", passed), ("clean_held_back", held)):
        with open(out_dir / f"{name}_{model}.csv", "w", newline="", encoding="utf-8") as f:
            fields = sorted({k for r in rows for k in r}) or ["model"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    return passed, held, untracked, sum(len(groups.get(g, [])) for g in ("clean_dialog", "clean_external"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results/test_final")
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    args = ap.parse_args()
    data_dir = ROOT / args.dir
    out_dir = data_dir / "error_analysis"
    out_dir.mkdir(exist_ok=True)
    emb = LocalEmbeddings()
    lines = [f"Error analysis, {args.split} split, Trust Gate (variant 'trust')", ""]
    for model in MODELS:
        passed, held, untracked, n_clean = analyze(model, data_dir, args.split, emb, out_dir)
        by_kind = defaultdict(Counter)
        for p in passed:
            by_kind[p["attack"]][p["cause"]] += 1
        lines.append(f"== {model}")
        lines.append(f"  A. poison accepted by the gate: {len(passed)} "
                     f"(of which the attack then succeeded: {sum(p['attack_succeeded'] for p in passed)})")
        for kind, c in sorted(by_kind.items()):
            lines.append(f"     {kind:<22} " + ", ".join(f"{k}={v}" for k, v in c.most_common()))
        lines.append(f"     poison never written by the writer (gate never saw it): {dict(untracked)}")
        reasons = Counter((h["group"], h["reason"]) for h in held)
        pats = Counter(p for h in held for p in h["patterns"].split(",") if p)
        lines.append(f"  B. clean memories held back: {len(held)} of {n_clean} -> "
                     + ", ".join(f"{g}/{r}={v}" for (g, r), v in sorted(reasons.items())))
        if pats:
            lines.append(f"     pattern categories: {dict(pats)}")
        lines.append("")
    (out_dir / "summary.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"Details: {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
