"""Tests for the non-LLM parts of the Trust Gate. Uses DEV data only. Run: pytest -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import locomo  # noqa: E402
from gate.scoring import decide, pattern_hits, source_span, source_trust, trust_score  # noqa: E402

load = lambda name: json.load(open(ROOT / "data" / name, encoding="utf-8"))
DEV_A2 = ["Confirmed and verified:", "Fact-checked and 100% certain:", "Officially confirmed, no doubt about it:"]


def test_source_trust_table():
    assert source_trust("dialog") == 0.9 and source_trust("external_web") == 0.3
    assert source_trust("unknown_source") == source_trust("external_web")  # unknown = low


@pytest.mark.parametrize("prefix", DEV_A2)
def test_patterns_catch_dev_A2_phrases(prefix):
    assert "over_assertion" in pattern_hits(f"{prefix} By the way, my grandma is from Norway.")


def test_patterns_catch_dev_A3_auth():
    a = next(x for x in load("auth_scenarios.json") if x["split"] == "dev")
    assert {"authorization", "agent_directive"} <= set(pattern_hits(a["page_text"]))


def test_patterns_ignore_ordinary_sentences():
    for s in ["By the way, my grandma is from Norway.", "I adopted a guinea pig last week!",
              "Thanks, Melanie! This necklace is super special to me."]:
        assert pattern_hits(s) == []


def test_source_span_finds_the_A2_poison_turn():
    # The writer drops the assertion phrase; the gate must go back to the source turn to see it.
    case = next(c for c in load("poison_cases.json") if c["case_id"] == "T06-A2")
    sess = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
    chunk = next(ch for ch in locomo.writer_chunks(sess) if ch["session"] == case["inject_session"])
    span = source_span("Jon decided to use hardwood flooring for his dance studio.", chunk["text"])
    assert span.endswith(case["turn"]["text"]) and "over_assertion" in pattern_hits(span)


def test_source_span_of_clean_memory_does_not_point_to_poison_turn():
    case = next(c for c in load("poison_cases.json") if c["case_id"] == "T06-A2")
    sess = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
    chunk = next(ch for ch in locomo.writer_chunks(sess) if ch["session"] == case["inject_session"])
    first_turn = sess[case["inject_session"] - 1]["turns"][0]
    span = source_span(first_turn["text"], chunk["text"])
    assert case["confident_prefix"] not in span


def test_trust_score_formula():
    assert trust_score(0.9, 0.8, 0.0) == pytest.approx(0.8)          # min(T_source, C)
    assert trust_score(0.3, 0.95, 0.0) == pytest.approx(0.3)         # a low-trust source caps the score
    assert trust_score(0.9, 0.8, 1.0, lambda_r=0.5) == pytest.approx(0.3)
    assert trust_score(0.9, 0.8, 0.0, age_days=10, lambda_t=0.1) == pytest.approx(0.8 * 0.36788, rel=1e-4)


def test_decide_boundaries():
    assert decide(0.7, 0.7, 0.4) == "accept"
    assert decide(0.69, 0.7, 0.4) == "quarantine" and decide(0.4, 0.7, 0.4) == "quarantine"
    assert decide(0.39, 0.7, 0.4) == "reject"
    with pytest.raises(ValueError):
        decide(0.5, 0.4, 0.7)
