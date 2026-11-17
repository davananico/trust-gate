"""
prepare_longmemeval.py — lists candidate target facts from LongMemEval (second dataset) for MANUAL review.

Input : data/raw/longmemeval/longmemeval_s_cleaned.json
        (https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned, MIT license; sha256 in docs/dataset2_plan.md)
Output: data/lme_candidates.json   +   data/lme_candidates.csv (same rows, for reading in a spreadsheet)

Two kinds of candidates:
  poison_target   single-session-user questions with a short answer stated literally in ONE user turn.
                  Used like the LoCoMo targets: A1/A2/A3 + a clean external page, built later from a hand-written
                  template + poison value (data/lme_targets_manual.json, not produced here).
  update_probe    knowledge-update questions: the user states a value, then a NEWER value in a later session.
                  No attack. Measures whether the gate rejects a legitimate update (the failure mode found in the
                  LoCoMo error analysis).
Deterministic; no LLM. Nothing here decides the final selection: the person reviews the candidates.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from textnorm import normalize  # noqa: E402

RAW = ROOT / "data" / "raw" / "longmemeval" / "longmemeval_s_cleaned.json"
MAX_ANSWER_WORDS = 4


def evidence(item):
    """[(session index, turn index, role, text)] of the turns marked has_answer."""
    return [(si, ti, t["role"], t["content"]) for si, s in enumerate(item["haystack_sessions"])
            for ti, t in enumerate(s) if t.get("has_answer")]


def main():
    data = json.load(open(RAW, encoding="utf-8"))
    out = []
    for it in data:
        if it["question_id"].endswith("_abs"):
            continue
        ev = evidence(it)
        user_ev = [e for e in ev if e[2] == "user"]
        base = {"question_id": it["question_id"], "question_type": it["question_type"], "question": it["question"],
                "answer": str(it["answer"]), "question_date": it["question_date"],
                "n_sessions": len(it["haystack_sessions"])}
        if it["question_type"] == "single-session-user":
            ans = normalize(str(it["answer"]))
            literal = [e for e in user_ev if ans and ans in normalize(e[3])]
            if len(ans.split()) <= MAX_ANSWER_WORDS and len({e[0] for e in literal}) == 1:
                si, ti, _, text = literal[0]
                out.append({**base, "kind": "poison_target", "evidence_session": si, "evidence_turn": ti,
                            "evidence_date": it["haystack_dates"][si], "evidence_text": text})
        elif it["question_type"] == "knowledge-update":
            sessions = sorted({e[0] for e in user_ev})
            if len(sessions) >= 2:
                old = next(e for e in user_ev if e[0] == sessions[0])
                new = next(e for e in user_ev if e[0] == sessions[-1])
                out.append({**base, "kind": "update_probe", "old_session": old[0], "old_text": old[3],
                            "new_session": new[0], "new_text": new[3],
                            "new_date": it["haystack_dates"][new[0]]})

    json.dump(out, open(ROOT / "data" / "lme_candidates.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    cols = sorted({k for r in out for k in r})
    with open(ROOT / "data" / "lme_candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    for kind in ("poison_target", "update_probe"):
        print(f"{kind}: {sum(r['kind'] == kind for r in out)}")


if __name__ == "__main__":
    main()
