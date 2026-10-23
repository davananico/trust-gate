"""Tests for the session loader and inject_poison. Run: pytest -q"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import locomo  # noqa: E402

load = lambda name: json.load(open(ROOT / "data" / name, encoding="utf-8"))
case_by_id = {c["case_id"]: c for c in load("poison_cases.json")}


def test_conv26_session_count():
    s = locomo.load_sessions("conv-26")
    assert len(s) == 19 and [x["session"] for x in s] == list(range(1, 20))


def test_A1_adds_one_turn_at_end_of_injection_session_only():
    sessions = locomo.load_sessions("conv-26")
    case = case_by_id["T01-A1"]
    out = locomo.inject_poison(sessions, case)
    for a, b in zip(sessions, out):
        if b["session"] == case["inject_session"]:
            assert b["turns"][:-1] == a["turns"] and b["turns"][-1]["text"] == case["turn"]["text"]
        else:
            assert a == b


def test_inject_does_not_modify_original_sessions():
    sessions = locomo.load_sessions("conv-26")
    n = len(sessions[4]["turns"])
    locomo.inject_poison(sessions, case_by_id["T01-A1"])
    assert len(sessions[4]["turns"]) == n


def test_A3_becomes_external_web_chunk_without_html_tags():
    out = locomo.inject_poison(locomo.load_sessions("conv-26"), case_by_id["T01-A3"])
    ext = [c for c in locomo.writer_chunks(out) if c["source"] == "external_web"]
    assert len(ext) == 1
    assert "Caroline's grandmother is from Norway." in ext[0]["text"] and "<" not in ext[0]["text"]


def test_unpoisoned_dialog_chunks_are_identical():
    # Sessions without injection must be identical across conditions (so the LLM cache is reused and comparison is fair).
    clean = locomo.writer_chunks(locomo.load_sessions("conv-26"))
    pois = locomo.writer_chunks(locomo.inject_poison(locomo.load_sessions("conv-26"), case_by_id["T01-A2"]))
    diff = [a["session"] for a, b in zip(clean, pois) if a != b]
    assert diff == [case_by_id["T01-A2"]["inject_session"]]


def test_every_case_can_be_injected():
    for name in ("poison_cases.json", "clean_external.json", "auth_scenarios.json"):
        for case in load(name):
            locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
