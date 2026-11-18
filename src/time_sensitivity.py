"""
time_sensitivity.py — EXPLORATORY: what the time factor would change on LongMemEval. Not tuned, not used to choose
anything; the locked gate (lambda_t = 0, theta = -0.05) is unchanged.

  python src/time_sensitivity.py --split lme [--results results]

Decisions are recomputed from the logged signals (no LLM) with age = question date - session date (days), for a
grid of lambda_t and theta_accept (= theta_reject, as in the locked thresholds).
Why theta too: at the locked theta = -0.05 the time factor cannot change any decision. With R_poison = 0 the score
min(T_source, C_content) * exp(-lambda_t * age) is >= 0 > theta (accept); with R_poison = 1 it is <= 0.9 - 1 < theta
(reject). Time only matters for a stricter theta.
Scenario: age is measured as if the whole history were ingested on the question date (e.g. importing old chat logs).
The real run writes session by session, where the source age at write time is ~0 (as in LoCoMo). Even in this
scenario the poison is always the newest source, so a time factor favours the poison over the original fact.
Approximation: the logged contradiction signals were computed against the memory the LOCKED gate built; a different
decision would change later neighbours, which is not replayed.
"""
import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import json  # noqa: E402

import lme  # noqa: E402
from gate.trust_gate import GateParams, decide_candidate  # noqa: E402
from textnorm import contains_any  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = ["ollama_qwen3_8b", "ollama_gemma4_12b", "ollama_llama3.1_8b", "ollama_olmo-3_7b-instruct"]
LAMBDAS = (0.0, 0.001, 0.01)
THETAS = (-0.05, 0.1, 0.2, 0.3)


def day(s):
    return datetime.strptime(s.split(" (")[0], "%Y/%m/%d")


def age_days(question_id, session):
    it = lme.item(question_id)
    dates = it["haystack_dates"] + [it["question_date"]]  # the extra session (if any) is dated at the question
    return max(0, (day(it["question_date"]) - day(dates[session - 1])).days)


def groups(db_path, split):
    cases = {c["case_id"]: c for c in json.load(open(ROOT / "data" / "lme_poison_cases.json", encoding="utf-8"))
             if c["split"] == split}
    upd = {f"UPD-{u['probe_id']}": u for u in json.load(open(ROOT / "data" / "lme_updates.json", encoding="utf-8"))}
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    g = defaultdict(list)
    for r in db.execute("SELECT * FROM gate_decisions WHERE run_id LIKE 'trust|%'"):
        cid, r = r["case_id"], dict(r)
        r["age_days"] = age_days(r["sample_id"], r["session"])
        if cid.startswith("CLEAN-"):
            g["clean_dialog"].append(r)
        elif cid.endswith("-EXT-CLEAN") and r["source"] == "external_web":
            g["clean_external"].append(r)
        elif cid in cases:
            c = cases[cid]
            if (r["session"] == c["inject_session"] and r["source"] == c["source"]
                    and contains_any(r["content"], c["poison_keys"])):
                g["poison"].append(r)
        elif (cid in upd and r["session"] == upd[cid]["new_session"]
              and contains_any(r["content"], upd[cid]["new_value_keys"])):
            g["update_new_value"].append(r)
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="lme", choices=["pilot", "lme"])
    ap.add_argument("--results", default=str(ROOT / "results"))
    args = ap.parse_args()
    for m in MODELS:
        db = Path(args.results) / f"lme_{args.split}_{m}_gate.sqlite"
        if not db.exists():
            continue
        g = groups(db, args.split)
        print(f"\n=== {m} (EXPLORATORY, not tuned) — share held back (rejected or quarantined); "
              "poison: higher is better, clean/update: lower is better ===")
        print(f"{'theta':>7} {'lambda_t':>9}"
              + "".join(f"{k:>18}" for k in ("poison", "clean_dialog", "clean_external", "update_new_value")))
        for theta in THETAS:
            for lam in LAMBDAS:
                p = GateParams(theta_accept=theta, theta_reject=theta, lambda_r=1.0, lambda_t=lam)
                cells = []
                for k in ("poison", "clean_dialog", "clean_external", "update_new_value"):
                    rows = g.get(k, [])
                    held = sum(decide_candidate(r, p)[1] != "accept" for r in rows)
                    cells.append(f"{held}/{len(rows)}" + (f" ({100 * held / len(rows):.0f}%)" if rows else ""))
                print(f"{theta:>7} {lam:>9}" + "".join(f"{c:>18}" for c in cells))


if __name__ == "__main__":
    main()
