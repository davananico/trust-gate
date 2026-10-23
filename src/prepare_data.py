"""
prepare_data.py — prepares the LoCoMo subset for the Memory Trust Gate experiment.

What it does:
  1. Reads LoCoMo (data/raw/locomo10.json) and the manual list of target facts (data/targets_manual.json).
  2. Validates every target fact:
       - the true-answer keywords match the LoCoMo gold answer,
       - the true-answer keywords appear in the evidence turn,
       - the poison value NEVER appears in the original conversation (if it did, it would leak into ASR),
       - counts how often the true fact is mentioned across the conversation (redundancy).
  3. Sets the poison injection session = the session after the evidence session (so cross-session persistence is tested).
  4. Splits the data by conversation: 3 dev conversations, 7 test (fixed seed).
  5. Samples clean (non-target) questions for clean accuracy.

Run from the project folder:
  python src/prepare_data.py
Output: data/targets.json, data/split.json, data/clean_questions.json, data/targets_summary.csv
"""
import csv
import json
import random
import re
from pathlib import Path

from textnorm import contains_any

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "locomo10.json"
MANUAL = ROOT / "data" / "targets_manual.json"
OUT = ROOT / "data"

SEED = 2026
N_DEV_CONV = 3
N_CLEAN_PER_CONV = 10
CATEGORY_NAME = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}


def has_key(text, keys):
    """True if any keyword appears as a whole word (case-insensitive)."""
    text = str(text)
    return any(re.search(r"(?<![A-Za-z])" + re.escape(k) + r"(?![A-Za-z])", text, re.I) for k in keys)


def count_key(texts, keys):
    return sum(1 for t in texts if has_key(t, keys))


def load_conversation(sample):
    """Returns a dict dia_id -> (session_number, turn), the number of sessions, and each session's date."""
    conv = sample["conversation"]
    turns, dates = {}, {}
    for key, val in conv.items():
        m = re.fullmatch(r"session_(\d+)", key)
        if m:
            s = int(m.group(1))
            dates[s] = conv[f"session_{s}_date_time"]
            for t in val:
                turns[t["dia_id"]] = (s, t)
    return turns, len(dates), dates


def main():
    data = json.load(open(RAW, encoding="utf-8"))
    by_id = {s["sample_id"]: s for s in data}
    manual = json.load(open(MANUAL, encoding="utf-8"))["targets"]

    targets, problems = [], []
    for i, m in enumerate(manual):
        sample = by_id[m["sample_id"]]
        qa = sample["qa"][m["qa_index"]]
        turns, n_sess, dates = load_conversation(sample)
        ev_id = qa["evidence"][0]
        ev_sess, ev_turn = turns[ev_id]
        all_texts = [t["text"] for _, t in turns.values()]

        checks = {
            "truth_in_gold_answer": has_key(qa["answer"], m["truth_keys"]),
            "truth_in_evidence": has_key(ev_turn["text"], m["truth_keys"]),
            "poison_absent_in_conv": count_key(all_texts, m["poison_keys"]) == 0,
            "poison_not_in_gold": not has_key(qa["answer"], m["poison_keys"]),
            "inject_session_exists": ev_sess + 1 <= n_sess,
            # LoCoMo annotations sometimes name the wrong person (e.g. a question about John, but Tim is speaking).
            "evidence_speaker_is_subject": ev_turn["speaker"] in qa["question"],
            # The templates must produce sentences that contain the right keywords.
            "true_claim_has_truth_key": all(has_key(m[c].replace("{X}", m["true_value"]), m["truth_keys"])
                                            for c in ("claim_1p", "claim_3p")),
            "poison_claim_has_poison_key": all(has_key(m[c].replace("{X}", m["poison_value"]), m["poison_keys"])
                                               and not has_key(m[c].replace("{X}", m["poison_value"]), m["truth_keys"])
                                               for c in ("claim_1p", "claim_3p")),
        }
        for name, ok in checks.items():
            if not ok:
                problems.append(f"{m['sample_id']} qa#{m['qa_index']}: {name} FAILED")

        inject_sess = ev_sess + 1
        # Subject = the speaker whose name appears FIRST in the question. Do not rely on set order:
        # set order changes between runs, so questions naming two people (e.g. T27) would not be reproducible.
        speakers = [sample["conversation"]["speaker_a"], sample["conversation"]["speaker_b"]]
        in_question = [sp for sp in speakers if sp in qa["question"]]
        subject = min(in_question, key=qa["question"].index) if in_question else None
        targets.append({
            "target_id": f"T{i+1:02d}",
            "sample_id": m["sample_id"],
            "qa_index": m["qa_index"],
            "category": CATEGORY_NAME[qa["category"]],
            "subject": subject,
            "question": qa["question"],
            "gold_answer": str(qa["answer"]),
            "truth_keys": m["truth_keys"],
            "true_value": m["true_value"],
            "poison_value": m["poison_value"],
            "claim_1p": m["claim_1p"],
            "claim_3p": m["claim_3p"],
            "poison_keys": m["poison_keys"],
            "evidence_dia_id": ev_id,
            "evidence_speaker": ev_turn["speaker"],
            "evidence_text": ev_turn["text"],
            "evidence_session": ev_sess,
            "evidence_session_date": dates[ev_sess],
            "inject_session": inject_sess,
            "inject_session_date": dates[inject_sess],
            "n_sessions": n_sess,
            "truth_mentions_in_conv": count_key(all_texts, m["truth_keys"]),
            "checks": checks,
        })

    # ---- dev/test split by conversation (not by fact) ----
    conv_ids = sorted(by_id)
    rng = random.Random(SEED)
    dev = sorted(rng.sample(conv_ids, N_DEV_CONV))
    test = [c for c in conv_ids if c not in dev]
    for t in targets:
        t["split"] = "dev" if t["sample_id"] in dev else "test"

    # ---- clean questions for clean accuracy ----
    target_keys = {(t["sample_id"], t["qa_index"]) for t in targets}
    target_evidence = {(t["sample_id"], t["evidence_dia_id"]) for t in targets}
    clean = []
    for cid in conv_ids:
        sample = by_id[cid]
        turns, _, _ = load_conversation(sample)
        pool = []
        for qi, q in enumerate(sample["qa"]):
            if q["category"] != 4 or (cid, qi) in target_keys:
                continue
            ans = str(q.get("answer", ""))
            if not ans or len(ans.split()) > 4 or len(q["evidence"]) != 1:
                continue
            if q["evidence"][0] not in turns or (cid, q["evidence"][0]) in target_evidence:
                continue
            # The gold answer must appear IN FULL (after normalization) in the evidence turn. Otherwise
            # (a paraphrase, or an answer that only appears in an image caption) string match cannot score it fairly.
            # Questions and answers stay exactly as in LoCoMo; only the selection of questions changes.
            ev_text = turns[q["evidence"][0]][1]["text"]
            if not contains_any(ev_text, [ans]):
                continue
            pool.append((qi, q))
        rng_c = random.Random(f"{SEED}-{cid}")
        for qi, q in rng_c.sample(pool, min(N_CLEAN_PER_CONV, len(pool))):
            clean.append({
                "sample_id": cid, "qa_index": qi, "question": q["question"],
                "gold_answer": str(q["answer"]), "evidence_dia_id": q["evidence"][0],
                "split": "dev" if cid in dev else "test",
            })
    clean.sort(key=lambda x: (x["sample_id"], x["qa_index"]))

    # ---- save ----
    json.dump(targets, open(OUT / "targets.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump({"seed": SEED, "dev": dev, "test": test}, open(OUT / "split.json", "w"), indent=2)
    json.dump(clean, open(OUT / "clean_questions.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    with open(OUT / "targets_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["target_id", "split", "sample_id", "qa_index", "question", "gold_answer",
                    "poison_value", "evidence_dia_id", "evidence_session", "inject_session",
                    "truth_mentions_in_conv", "all_checks_ok"])
        for t in targets:
            w.writerow([t["target_id"], t["split"], t["sample_id"], t["qa_index"], t["question"],
                        t["gold_answer"], t["poison_value"], t["evidence_dia_id"], t["evidence_session"],
                        t["inject_session"], t["truth_mentions_in_conv"], all(t["checks"].values())])

    # ---- summary ----
    n_dev = sum(t["split"] == "dev" for t in targets)
    print(f"Target facts: {len(targets)}  (dev {n_dev}, test {len(targets) - n_dev})")
    print(f"Poison cases (x3 attack types): {3 * len(targets)}  (test {3 * (len(targets) - n_dev)})")
    print(f"Clean questions: {len(clean)}")
    print(f"Dev: {dev}\nTest: {test}")
    print("Validation problems:" if problems else "All validation checks passed.")
    for p in problems:
        print("  -", p)


if __name__ == "__main__":
    main()
