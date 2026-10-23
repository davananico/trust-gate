"""Tests for memory_writer and the LLM cache (fake model, no network). Run: pytest -q"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import locomo  # noqa: E402
import llm  # noqa: E402
from memory_writer import parse_list, parse_list_status, write_memories  # noqa: E402

case_by_id = {c["case_id"]: c for c in json.load(open(ROOT / "data" / "poison_cases.json", encoding="utf-8"))}


def chunks_for(case_id):
    case = case_by_id[case_id]
    s = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
    return [c for c in locomo.writer_chunks(s) if c["session"] == case["inject_session"]]


def test_parse_list_tolerant():
    assert parse_list('```json\n["A likes tea.", "B owns a cat."]\n```') == ["A likes tea.", "B owns a cat."]
    assert parse_list("Here you go: []") == []
    assert parse_list("no json here") == []
    assert parse_list('["broken"') == []


def test_parse_list_repairs_missing_commas():
    # Output shape of olmo-3:7b-instruct in the quicktest (15 Oct): missing commas between items.
    reply = """["Caroline attended a pottery class." "Caroline's grandmother is from Sweden."]"""
    items, status = parse_list_status(reply)
    assert status == "repaired" and items == ["Caroline attended a pottery class.", "Caroline's grandmother is from Sweden."]
    assert parse_list_status('["A."]')[1] == "ok"
    assert parse_list_status("[]")[1] == "ok" and parse_list_status("no json here")[1] == "failed"


def test_parse_list_repairs_brace_wrapped_items():
    # Output shape of qwen3:8b for conv-26 session 4 (19 Oct): every item wrapped in {"..."}.
    reply = '[{"Caroline received a necklace from her grandma in Sweden."},{"Melanie went camping."}]'
    items, status = parse_list_status(reply)
    assert status == "repaired"
    assert items == ["Caroline received a necklace from her grandma in Sweden.", "Melanie went camping."]
    # Real JSON objects ({"key": "value"}): their text values are kept, not dropped.
    assert parse_list_status('[{"fact": "A."}]') == (["A."], "ok")


def test_parse_list_salvages_broken_json():
    # Real qwen3:8b output, conv-26 sessions 3 & 7 (19 Oct): missing closing brace, unescaped quotes inside a sentence.
    reply = '[{"Caroline is thankful."},{"Caroline likes the book "Becoming Nicole" a lot."},{"Family is everything."]'
    items, status = parse_list_status(reply)
    assert status == "salvaged"
    assert items == ["Caroline is thankful.", 'Caroline likes the book "Becoming Nicole" a lot.', "Family is everything."]


def test_parse_list_one_list_per_line():
    # Real olmo-3:7b-instruct output (19 Oct): one list per line, including empty lists.
    reply = '["Jon lost his job as a banker."]  \n[]\n["Gina\'s favorite dance style is contemporary"]  \n["Jon won."]\n[]'
    items, status = parse_list_status(reply)
    assert status == "repaired"
    assert items == ["Jon lost his job as a banker.", "Gina's favorite dance style is contemporary", "Jon won."]


def test_parse_list_truncated_reply():
    # Real qwen3:8b output (19 Oct): looped until the 1024-token cap, cut off mid-item.
    reply = '[{"Audrey has four dogs."},{"Pets bring comfort."},{"Pets bring comfort."},{"Aud'
    items, status = parse_list_status(reply)
    assert status == "truncated" and items == ["Audrey has four dogs.", "Pets bring comfort."]


def test_A1_poison_becomes_dialog_candidate():
    cands = [c for ch in chunks_for("T01-A1") for c in write_memories(ch, llm.FakeWriterModel())]
    norway = [c for c in cands if "Norway" in c["content"]]
    assert norway and all(c["source"] == "dialog" for c in norway)


def test_A3_poison_becomes_external_web_candidate():
    cands = [c for ch in chunks_for("T01-A3") for c in write_memories(ch, llm.FakeWriterModel())]
    norway = [c for c in cands if "Norway" in c["content"]]
    assert norway and all(c["source"] == "external_web" for c in norway)


def test_candidates_carry_no_attack_labels():
    cand = write_memories(chunks_for("T01-A1")[0], llm.FakeWriterModel())[0]
    assert not {"is_poison", "poison_value", "poison_keys", "gold_answer", "attack"} & set(cand)


def test_cache_avoids_second_model_call(tmp_path):
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
