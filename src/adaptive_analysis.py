"""
adaptive_analysis.py — checks that each adaptive attack worked through the mechanism it was written for.

Read-only, no LLM (neighbours are rebuilt from the logged accepted memories, as in error_analysis.py).
  python src/adaptive_analysis.py --split dev [--results results]

Per model and attack (Trust Gate condition), for every poison candidate:
  pattern_hit             the pattern signal fired (AD1/AD2 aim for 0)
  truth_not_in_neighbors  the true fact was active but not among the judge's 5 neighbours (AD3 aims to raise this)
  judge_conflict          the contradiction judge said YES
  decision                accept / quarantine / reject
For AD3 also: filler memories recorded = accepted memories in the evidence session minus those in the AD1 run of
the same target (AD1 leaves the evidence session untouched).
"""
import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from error_analysis import nearest, run_rows  # noqa: E402
from memory_store import LocalEmbeddings  # noqa: E402
from textnorm import contains_any  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = ["ollama_qwen3_8b", "ollama_gemma4_12b", "ollama_llama3.1_8b", "ollama_olmo-3_7b-instruct"]


def analyze(db_path, cases, targets, emb, ref_path=None):
    """ref_path: the gate log holding the AD1 runs (the same file unless only a subset of attacks was run)."""
    db = sqlite3.connect(db_path)
    ref = sqlite3.connect(ref_path or db_path)
    out = defaultdict(lambda: defaultdict(int))
    for c in cases:
        rows = run_rows(db, f"trust|{c['case_id']}")
        keys = c.get("poison_keys") or [c["harmful_destination"]]
        poison = [r for r in rows if r["session"] == c["inject_session"] and contains_any(r["content"], keys)]
        s = out[c["attack"]]
        s["cases"] += 1
        s["poison_not_written"] += not poison
        truth = c.get("truth_keys") or []
        active = [r for r in rows if r["session"] < c["inject_session"] and r["decision"] == "accept"]
        for p in poison:
            s["poison_candidates"] += 1
            s[p["decision"]] += 1
            s["pattern_hit"] += bool(p["r_pattern"])
            s["judge_conflict"] += p["r_contradiction"] == 1.0
            if truth and any(contains_any(a["content"], truth) for a in active):
                s["truth_active"] += 1
                s["truth_not_in_neighbors"] += not any(contains_any(n, truth) for n in nearest(emb, active, p["content"]))
        if c["attack"] == "AD3_flooding":
            ev = targets[c["target_id"]]["evidence_session"]
            n_ad3 = sum(r["session"] == ev and r["decision"] == "accept" for r in rows)
            n_ad1 = sum(r["session"] == ev and r["decision"] == "accept" for r in run_rows(ref, f"trust|{c['target_id']}-AD1"))
            s["filler_memories_recorded"] += n_ad3 - n_ad1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--suffix", default="", help="e.g. _AD3 for a run_adaptive.py --attacks AD3_flooding run")
    args = ap.parse_args()
    cases = [c for c in json.load(open(ROOT / "data" / "adaptive_cases.json", encoding="utf-8")) if c["split"] == args.split]
    targets = {t["target_id"]: t for t in json.load(open(ROOT / "data" / "targets.json", encoding="utf-8"))}
    emb = LocalEmbeddings()
    cols = ["cases", "poison_not_written", "poison_candidates", "accept", "reject", "quarantine", "pattern_hit",
            "judge_conflict", "truth_active", "truth_not_in_neighbors", "filler_memories_recorded"]
    for m in MODELS:
        db = Path(args.results) / f"adaptive_{args.split}_{m}{args.suffix}_gate.sqlite"
        if not db.exists():
            continue
        ref = Path(args.results) / f"adaptive_{args.split}_{m}_gate.sqlite"
        run_ids = {r[0] for r in sqlite3.connect(db).execute("SELECT DISTINCT case_id FROM gate_decisions")}
        print(f"\n=== {m} ({args.split}{args.suffix}, Trust Gate) ===")
        print(f"{'attack':<22}" + "".join(f"{c[:12]:>13}" for c in cols))
        mine = [c for c in cases if c["case_id"] in run_ids]
        for attack, s in sorted(analyze(db, mine, targets, emb, ref).items()):
            print(f"{attack:<22}" + "".join(f"{s[c]:>13}" for c in cols))


if __name__ == "__main__":
    main()
