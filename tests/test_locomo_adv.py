"""Tests for the ported LoCoMo-Adv text attacks (src/make_locomo_adv_cases.py). Run: pytest -q"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import locomo  # noqa: E402
from make_locomo_adv_cases import FAMILIES, build, inject_pages  # noqa: E402

TARGETS = json.load(open(ROOT / "data" / "targets.json", encoding="utf-8"))


def test_cases_are_deterministic_and_match_the_saved_file():
    saved = json.load(open(ROOT / "data" / "locomo_adv_cases.json", encoding="utf-8"))
    assert build(TARGETS) == build(TARGETS) == saved
    assert len(saved) == len(TARGETS) * len(FAMILIES)


def test_only_fact_overwrite_states_the_poison_value():
    t = TARGETS[0]
    for c in build([t]):
        text = " ".join(p["text"] for p in c["pages"])
        assert (t["poison_value"] in text) == (c["attack"] == "LA_fact_overwrite")
        assert bool(c["poison_keys"]) == (c["attack"] == "LA_fact_overwrite")


def test_inject_pages_adds_pages_to_the_injection_session_only():
    case = next(c for c in build(TARGETS[:1]) if c["attack"] == "LA_visual_prompt_injection")
    sessions = locomo.load_sessions(case["sample_id"])
    out = inject_pages(sessions, case)
    added = {s["session"]: len(s["pages"]) - len(o["pages"]) for s, o in zip(out, sessions)}
    assert added[case["inject_session"]] == 2 and sum(added.values()) == 2
    assert all(o["pages"] == [] for o in sessions)  # the original sessions are not modified
    chunks = [c for c in locomo.writer_chunks(out) if c["source"] == "external_web"]
    assert len(chunks) == 2 and not any("LA_" in c["text"] for c in chunks)  # labels never reach the writer
