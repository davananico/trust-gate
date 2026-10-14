"""Tes memory_writer dan cache LLM (model palsu, tanpa internet). Jalankan: pytest -q"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import locomo  # noqa: E402
import llm  # noqa: E402
from memory_writer import parse_list, write_memories  # noqa: E402

case_by_id = {c["case_id"]: c for c in json.load(open(ROOT / "data" / "poison_cases.json", encoding="utf-8"))}


def chunks_for(case_id):
    case = case_by_id[case_id]
    s = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
    return [c for c in locomo.writer_chunks(s) if c["session"] == case["inject_session"]]


def test_parse_list_toleran():
    assert parse_list('```json\n["A likes tea.", "B owns a cat."]\n```') == ["A likes tea.", "B owns a cat."]
    assert parse_list("Here you go: []") == []
    assert parse_list("tidak ada json") == []
    assert parse_list('["rusak"') == []


def test_racun_A1_jadi_kandidat_dialog():
    cands = [c for ch in chunks_for("T01-A1") for c in write_memories(ch, llm.FakeWriterModel())]
    norway = [c for c in cands if "Norway" in c["content"]]
    assert norway and all(c["source"] == "dialog" for c in norway)


def test_racun_A3_jadi_kandidat_external_web():
    cands = [c for ch in chunks_for("T01-A3") for c in write_memories(ch, llm.FakeWriterModel())]
    norway = [c for c in cands if "Norway" in c["content"]]
    assert norway and all(c["source"] == "external_web" for c in norway)


def test_kandidat_tidak_membawa_label_serangan():
    cand = write_memories(chunks_for("T01-A1")[0], llm.FakeWriterModel())[0]
    assert not {"is_poison", "poison_value", "poison_keys", "gold_answer", "attack"} & set(cand)


def test_cache_tidak_memanggil_model_dua_kali(tmp_path):
    calls = []

    class Counting(llm.FakeWriterModel):
        def _generate(self, *a, **k):
            calls.append(1)
            return super()._generate(*a, **k)

    llm.enable_cache(tmp_path / "c.sqlite")
    try:
        ch, m = chunks_for("T01-A1")[0], Counting()
        assert write_memories(ch, m) == write_memories(ch, m)
        assert len(calls) == 1
    finally:
        llm.set_llm_cache(None)
