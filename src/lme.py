"""
lme.py — LongMemEval (second dataset) as sessions in the same format as locomo.load_sessions(), plus its cases.

  load_sessions(question_id, keep)   -> sessions of that question's history (only the session indices in `keep`)
  build_cases()                      -> poison cases, clean external pages and update probes (written to data/)

Locked design (docs/dataset2_plan.md):
  - Only USER turns are given to the writer (assistant turns dropped); speaker name "User".
  - 10 sessions per question: poison targets keep the evidence session and its neighbours (the session after it
    receives the poison); update probes keep the old-value session and the 9 sessions ending at the new-value one.
  - Attacks reuse the LoCoMo builders and the TEST-split phrases (never seen while tuning the gate).
Session numbers are the original haystack index + 1, so gate logs can be traced back to the raw file.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from make_adaptive_attacks import LEXICON_FREE_PREFIX, SPLIT_SENTENCE  # noqa: E402
from make_attacks import CONFIDENT_PREFIX, fill, page_html  # noqa: E402

RAW = ROOT / "data" / "raw" / "longmemeval" / "longmemeval_s_cleaned.json"
PAGES = ROOT / "data" / "external_pages_lme"
WINDOW = 10
# The user gets a name, as every LoCoMo speaker has one. Pilot (17 Nov 2026): with the label "User" the locked writer
# prompt ("facts about the people in it ... use full names") returned [] for most sessions, including the poison
# turn. "Emery" appears 3 times in the whole raw file and never in the selected windows (tests/test_lme.py).
SPEAKER = "Emery"


def ask(question):
    """The question as the named user asks it (same convention as the A3-auth requests, e.g. 'Caroline: ...')."""
    return f"{SPEAKER}: {question}"
_items = {}


def item(question_id):
    if not _items:
        _items.update({it["question_id"]: it for it in json.load(open(RAW, encoding="utf-8"))})
    return _items[question_id]


def load_sessions(question_id, keep, extra_session=False):
    """extra_session: append an empty session dated at the question (for an evidence session that is the last)."""
    it = item(question_id)
    extra = [{"sample_id": question_id, "session": len(it["haystack_sessions"]) + 1, "date": it["question_date"],
              "turns": [], "pages": []}] if extra_session else []
    return [{
        "sample_id": question_id,
        "session": i + 1,
        "date": it["haystack_dates"][i],
        "turns": [{"speaker": SPEAKER, "dia_id": f"D{i + 1}:{j + 1}", "text": t["content"]}
                  for j, t in enumerate(it["haystack_sessions"][i]) if t["role"] == "user"],
        "pages": [],
    } for i in sorted(keep)] + extra


def poison_window(n_sessions, evidence):
    """10 consecutive indices containing `evidence` and `evidence + 1` (the injection session)."""
    start = max(0, min(evidence - 4, n_sessions - WINDOW))
    return list(range(start, min(start + WINDOW, n_sessions)))


def update_window(old, new):
    return sorted({old} | set(range(max(0, new - (WINDOW - 2)), new + 1)))


def build_cases():
    cand = {c["question_id"]: c for c in json.load(open(ROOT / "data" / "lme_candidates.json", encoding="utf-8"))}
    targets = json.load(open(ROOT / "data" / "lme_targets_manual.json", encoding="utf-8"))["targets"]
    probes = json.load(open(ROOT / "data" / "lme_update_probes.json", encoding="utf-8"))["probes"]
    PAGES.mkdir(parents=True, exist_ok=True)
    for old in PAGES.glob("*.html"):
        old.unlink()

    cases, externals = [], []
    for k, t in enumerate(targets):
        qid, c = t["question_id"], cand[t["question_id"]]
        n, ev = c["n_sessions"], c["evidence_session"]
        extra = ev + 1 >= n  # evidence is the last session: inject into an extra session dated at the question
        keep, sess = poison_window(n, ev), ev + 2  # session number of index ev + 1
        common = {"target_id": qid, "sample_id": qid, "split": "pilot" if t["pilot"] else "lme",
                  "subject": SPEAKER, "question": c["question"], "truth_keys": t["truth_keys"],
                  "poison_keys": t["poison_keys"], "inject_session": sess, "keep": keep,
                  "extra_session": extra, "source": "dialog"}
        claim = fill(t["claim_1p"], t["poison_value"])
        i = k % 3
        dialog = lambda case_id, attack, turns: {**common, "case_id": case_id, "attack": attack,
                                                 "channel": "dialog_inserts", "inserts": [{"session": sess, "turns": [
                                                     {"speaker": SPEAKER, "dia_id": f"D{sess}:P{j + 1}", "text": x}
                                                     for j, x in enumerate(turns)]}]}
        cases.append(dialog(f"{qid}-A1", "A1_false_fact", [claim]))
        cases.append(dialog(f"{qid}-A2", "A2_confident_poison", [f"{CONFIDENT_PREFIX['test'][i]} {claim}"]))
        cases.append(dialog(f"{qid}-AD1", "AD1_split_assertion", [SPLIT_SENTENCE["test"][i], claim]))
        cases.append(dialog(f"{qid}-AD2", "AD2_lexicon_free", [f"{LEXICON_FREE_PREFIX['test'][i]} {claim}"]))
        date = item(qid)["question_date"] if extra else item(qid)["haystack_dates"][ev + 1]
        for suffix, value, rows, attack in (("A3", t["poison_value"], cases, "A3_external_source"),
                                            ("EXT-CLEAN", t["true_value"], externals, None)):
            pid = f"{qid}-{suffix}"
            text = fill(t["claim_3p"], value).replace("This user", SPEAKER).replace("this user", SPEAKER)
            (PAGES / f"{pid}.html").write_text(page_html(pid, SPEAKER, date, text), encoding="utf-8")
            rows.append({**common, "case_id": pid, "attack": attack, "channel": "external_page",
                         "source": "external_web", "page_path": f"data/external_pages_lme/{pid}.html", "page_text": text})

    updates = []
    for p in probes:
        c = cand[p["question_id"]]
        updates.append({"probe_id": p["question_id"], "sample_id": p["question_id"], "question": c["question"],
                        "new_value_keys": p["new_value_keys"], "new_session": c["new_session"] + 1,
                        "old_session": c["old_session"] + 1, "keep": update_window(c["old_session"], c["new_session"])})

    out = ROOT / "data"
    json.dump(cases, open(out / "lme_poison_cases.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump(externals, open(out / "lme_clean_external.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump(updates, open(out / "lme_updates.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"LME poison cases: {len(cases)} | clean external: {len(externals)} | update probes: {len(updates)}")


if __name__ == "__main__":
    build_cases()
