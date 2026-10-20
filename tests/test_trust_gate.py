"""Tes Trust Gate di graph (model palsu, embedding asli, kasus DEV). Jalankan: pytest -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import locomo  # noqa: E402
from gate.gate_log import GateLog  # noqa: E402
from gate.trust_gate import GateParams, decide_candidate, make_trust_gate  # noqa: E402
from graph import build_graph, run  # noqa: E402
from llm import FakeModel  # noqa: E402
from memory_store import LocalEmbeddings, MemoryStore  # noqa: E402

case_by_id = {c["case_id"]: c for c in json.load(open(ROOT / "data" / "poison_cases.json", encoding="utf-8"))}
SIG = {"t_source": 0.3, "c_content": 0.9, "r_contradiction": 0.0, "r_pattern": 0.0, "age_days": 0.0}


@pytest.fixture(scope="module")
def emb():
    return LocalEmbeddings()


def run_gate(case_id, emb, tmp_path, params=GateParams()):
    case = case_by_id[case_id]
    llm = FakeModel(cache=False)
    store, log = MemoryStore(emb), GateLog(tmp_path / "gate.sqlite")
    out = run(build_graph(llm, gate=make_trust_gate(llm, params)), store,
              locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case),
              [{"qid": "q", "text": case["question"]}], case_id=case_id, gate_log=log)
    return case, out, log


def test_decide_candidate_mode_dan_ablation():
    p = GateParams(theta_accept=0.5, theta_reject=0.2)
    assert decide_candidate(SIG, p) == (pytest.approx(0.3), "quarantine")                      # sumber eksternal
    assert decide_candidate(SIG, GateParams(use_source_trust=False))[1] == "accept"            # ablation source trust
    assert decide_candidate({**SIG, "t_source": 0.9, "r_pattern": 1.0}, p)[1] == "reject"      # pola -> R_poison = 1
    assert decide_candidate({**SIG, "t_source": 0.9, "r_pattern": 1.0}, GateParams(use_poison_risk=False))[1] == "accept"
    assert decide_candidate(SIG, GateParams(mode="content_only"))[1] == "accept"               # konten saja: C = 0.9


def test_racun_A2_ditolak_dan_tidak_masuk_memori(emb, tmp_path):
    case, out, log = run_gate("T06-A2", emb, tmp_path)
    rejected = [r[0] for r in log.db.execute("SELECT content FROM rejected_log")]
    assert any("hardwood" in c.lower() for c in rejected)           # racun A2 tertolak karena pola di turn asal
    assert not any("hardwood" in m["content"].lower() for m in out["retrieved"]["q"])
    assert log.count() == sum(e["n_candidates"] for e in out["log"])  # SEMUA kandidat tercatat


def test_racun_A3_dikarantina_dan_tidak_masuk_memori(emb, tmp_path):
    case, out, log = run_gate("T06-A3", emb, tmp_path)
    assert log.count("memory_quarantine") > 0
    assert all(m["source"] == "dialog" for m in out["retrieved"]["q"])  # agen tidak pernah melihat sumber eksternal
    srcs = {r[0] for r in log.db.execute("SELECT source FROM memory_quarantine")}
    assert srcs == {"external_web"}


def test_gate_tidak_menerima_label_serangan(emb, tmp_path):
    _, _, log = run_gate("T06-A1", emb, tmp_path)
    cols = [r[1] for r in log.db.execute("PRAGMA table_info(gate_decisions)")]
    assert not {"is_poison", "poison_value", "poison_keys", "truth_keys", "gold_answer", "attack"} & set(cols)
