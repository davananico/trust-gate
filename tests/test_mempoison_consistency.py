"""MemPoison consistency baseline (port of their substrates.py). Run: pytest -q"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from gate.mempoison_consistency import consistency_conflict_score as score  # noqa: E402
from gate.mempoison_consistency import special_tokens  # noqa: E402
from gate.trust_gate import GateParams, decide_candidate  # noqa: E402


def test_empty_memory_or_no_shared_word_gives_zero():
    assert score("Caroline's grandma is from Norway.", []) == 0.0
    assert score("Caroline's grandma is from Norway.", ["Jon opened a dance studio"]) == 0.0


def test_sentence_final_period_makes_a_special_token():
    # their regex keeps '.', so the last word of a sentence counts as "special" (kept on purpose: faithful port)
    assert special_tokens("Grandma is from Norway.") == {"norway."}
    assert special_tokens("Grandma is from Norway") == set()


def test_formula_by_hand():
    # incoming {grandma, is, from, norway.}, existing {grandma, is, from, sweden.}: anchor 3/4, special mismatch 1
    assert score("Grandma is from Norway.", ["Grandma is from Sweden."]) == pytest.approx(0.45 * 0.75 + 0.35)
    # same without periods: no special tokens -> 0.45 * 0.75 only, below 0.58
    assert score("Grandma is from Norway", ["Grandma is from Sweden"]) == pytest.approx(0.3375)
    # update word "now" adds 0.2
    assert score("Grandma now lives in Norway", ["Grandma lives in Sweden"]) == pytest.approx(0.45 * 3 / 4 + 0.2)
    # max over all memories, capped at 1
    assert score("a b c now", ["a b c x.", "a b c"]) == pytest.approx(min(1.0, 0.45 + 0.2))


def test_runs_inside_the_graph_without_llm_calls(tmp_path):
    import json

    import locomo
    from gate.gate_log import GateLog
    from gate.trust_gate import make_trust_gate
    from graph import build_graph, run
    from llm import FakeModel
    from memory_store import LocalEmbeddings, MemoryStore

    case = next(c for c in json.load(open(ROOT / "data" / "poison_cases.json", encoding="utf-8")) if c["split"] == "dev")
    llm, log = FakeModel(cache=False), GateLog(tmp_path / "gate.sqlite")
    store = MemoryStore(LocalEmbeddings())
    run(build_graph(llm, gate=make_trust_gate(llm, GateParams(mode="mempoison_consistency"))), store,
        locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case), [], case_id=case["case_id"], gate_log=log)
    rows = log.db.execute("SELECT c_content, r_contradiction, t_final, decision, gate_mode FROM gate_decisions").fetchall()
    assert rows and all(r[0] is None and r[1] is None for r in rows)       # no LLM signal computed
    assert {r[4] for r in rows} == {"mempoison_consistency"}
    assert all((r[3] == "reject") == (-r[2] >= 0.58) for r in rows)
    assert store.count() == sum(r[3] == "accept" for r in rows)              # only accepted memories are stored


def test_decision_uses_the_fixed_threshold_only():
    p = GateParams(mode="mempoison_consistency", theta_accept=0.9, theta_reject=0.9)  # theta ignored
    assert not p.needs_contradiction
    assert decide_candidate({"r_consistency": 0.58}, p) == (-0.58, "reject")
    assert decide_candidate({"r_consistency": 0.5799}, p) == (-0.5799, "accept")
