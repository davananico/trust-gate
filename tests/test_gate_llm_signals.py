"""Tests for the Trust Gate LLM signals (fake model, no server). Run: pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from gate.llm_signals import (context_window, contradiction, content_confidence, parse_confidence,  # noqa: E402
                              parse_yes_no)
from llm import FakeModel  # noqa: E402


def test_parse_confidence():
    assert parse_confidence("8") == 0.8 and parse_confidence("Score: 7/10") == 0.7
    assert parse_confidence("0.6") == 0.6 and parse_confidence("10") == 1.0
    assert parse_confidence("no idea") is None and parse_confidence("42") is None


def test_parse_yes_no():
    assert parse_yes_no("YES") == 1.0 and parse_yes_no("No, they are compatible.") == 0.0
    assert parse_yes_no("maybe") is None


def test_context_window_takes_source_turn_and_neighbors():
    chunk = "A: hello there\nB: my grandma is from Sweden\nA: nice necklace\nB: thanks\nA: bye"
    assert context_window("Grandma is from Sweden", chunk) == "A: hello there\nB: my grandma is from Sweden\nA: nice necklace"


def test_signals_with_fake_model():
    llm = FakeModel(cache=False)
    assert content_confidence("Grandma is from Sweden", "B: my grandma is from Sweden", llm) == 0.9
    assert contradiction("Grandma is from Norway", ["Grandma is from Sweden"], llm) == 0.0
    assert contradiction("Grandma is from Norway", [], llm) == 0.0  # empty memory: no LLM call
