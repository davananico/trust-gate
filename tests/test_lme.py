"""LongMemEval loader and cases (second dataset). Needs data/raw/longmemeval/ (see docs/dataset2_plan.md). Run: pytest -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
if not (ROOT / "data" / "raw" / "longmemeval" / "longmemeval_s_cleaned.json").exists():
    pytest.skip("LongMemEval raw file not downloaded", allow_module_level=True)
import lme  # noqa: E402
from run_lme import sessions_for  # noqa: E402
from textnorm import contains_any  # noqa: E402

CASES = json.load(open(ROOT / "data" / "lme_poison_cases.json", encoding="utf-8"))
EXTERNALS = json.load(open(ROOT / "data" / "lme_clean_external.json", encoding="utf-8"))
UPDATES = json.load(open(ROOT / "data" / "lme_updates.json", encoding="utf-8"))


def test_windows_hold_ten_sessions_with_evidence_and_injection():
    for c in CASES:
        sessions = sessions_for(c)
        nums = [s["session"] for s in sessions]
        assert len(c["keep"]) == lme.WINDOW and nums == sorted(nums)
        assert c["inject_session"] in nums and c["inject_session"] - 1 in nums  # evidence + the session after it


def test_only_user_turns_reach_the_writer():
    c = CASES[0]
    raw = lme.item(c["sample_id"])["haystack_sessions"]
    for s in lme.load_sessions(c["sample_id"], c["keep"]):
        assert all(t["speaker"] == lme.SPEAKER for t in s["turns"])
        assert len(s["turns"]) == sum(t["role"] == "user" for t in raw[s["session"] - 1])


def test_poison_lands_in_the_injection_session_without_labels():
    for c in CASES:
        sessions = sessions_for(c)
        inj = next(s for s in sessions if s["session"] == c["inject_session"])
        text = json.dumps(inj)
        assert contains_any(text, c["poison_keys"]), c["case_id"]
        assert "poison_keys" not in json.dumps(sessions) and "A1_false_fact" not in json.dumps(sessions)


def test_clean_external_pages_carry_the_true_value_only():
    for c in EXTERNALS:
        assert contains_any(c["page_text"], c["truth_keys"]) and not contains_any(c["page_text"], c["poison_keys"])


def test_update_windows_hold_both_values():
    for u in UPDATES:
        nums = [s["session"] for s in sessions_for(u)]
        assert u["old_session"] in nums and u["new_session"] == nums[-1] and len(nums) <= lme.WINDOW


def test_user_name_never_occurs_in_the_selected_windows():
    import re
    for c in CASES + UPDATES:
        raw = lme.item(c["sample_id"])["haystack_sessions"]
        text = " ".join(t["content"] for i in c["keep"] for t in raw[i])
        assert not re.search(rf"\b{lme.SPEAKER}\b", text), c.get("case_id") or c["probe_id"]


def test_pilot_targets_are_fixed_and_separate():
    pilot = {c["target_id"] for c in CASES if c["split"] == "pilot"}
    assert pilot == {"e47becba", "118b2229", "58bf7951"}
    assert len({c["target_id"] for c in CASES if c["split"] == "lme"}) == 30
