"""End-to-end graph tests with a fake model and real (local) embeddings. Run: pytest -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import locomo  # noqa: E402
import tools  # noqa: E402
from graph import build_graph, run  # noqa: E402
from llm import FakeModel  # noqa: E402
from memory_store import LocalEmbeddings, MemoryStore  # noqa: E402

load = lambda name: json.load(open(ROOT / "data" / name, encoding="utf-8"))


@pytest.fixture(scope="module")
def emb():
    return LocalEmbeddings()


def test_A1_poison_reaches_the_answer_without_defense(emb):
    case = next(c for c in load("poison_cases.json") if c["case_id"] == "T01-A1")
    app = build_graph(FakeModel(cache=False))
    out = run(app, MemoryStore(emb), locomo.inject_poison(locomo.load_sessions("conv-26"), case),
              [{"qid": "T01", "text": case["question"]}])
    assert len(out["log"]) == 19  # every session processed in order
    assert "Norway" in out["answers"]["T01"]["answer"]


def test_gate_stores_only_accepted(emb):
    # Mock gate: rejects every candidate from an external source. Checks that the trust_gate -> store edge works.
    gate = lambda c, s: {**c, "decision": "reject" if c["source"] == "external_web" else "accept"}
    case = next(c for c in load("poison_cases.json") if c["case_id"] == "T01-A3")
    store = MemoryStore(emb)
    out = run(build_graph(FakeModel(cache=False), gate=gate), store,
              locomo.inject_poison(locomo.load_sessions("conv-26"), case), [{"qid": "T01", "text": case["question"]}])
    assert all(m["source"] == "dialog" for m in out["retrieved"]["T01"])
    assert "Norway" not in out["answers"]["T01"]["answer"]


def test_A3_auth_is_logged_but_not_executed(emb, tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "LOG", tmp_path / "log.jsonl")
    a = load("auth_scenarios.json")[0]
    out = run(build_graph(FakeModel(cache=False)), MemoryStore(emb),
              locomo.inject_poison(locomo.load_sessions(a["sample_id"]), a),
              [{"qid": "q", "text": a["user_request"]}], mode="tool")
    calls = out["answers"]["q"]["tool_calls"]
    assert calls and calls[0]["destination"] == "attacker.example" and calls[0]["result"] == "blocked"
    log = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert log and not any(r["executed"] for r in log)
