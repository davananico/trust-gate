"""Tes memory_writer dan cache LLM (model palsu, tanpa internet). Jalankan: pytest -q"""
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


def test_parse_list_toleran():
    assert parse_list('```json\n["A likes tea.", "B owns a cat."]\n```') == ["A likes tea.", "B owns a cat."]
    assert parse_list("Here you go: []") == []
    assert parse_list("tidak ada json") == []
    assert parse_list('["rusak"') == []


def test_parse_list_memperbaiki_koma_hilang():
    # Bentuk keluaran olmo-3:7b-instruct pada quicktest (15 Okt): koma antar-item hilang.
    reply = """["Caroline attended a pottery class." "Caroline's grandmother is from Sweden."]"""
    items, status = parse_list_status(reply)
    assert status == "repaired" and items == ["Caroline attended a pottery class.", "Caroline's grandmother is from Sweden."]
    assert parse_list_status('["A."]')[1] == "ok"
    assert parse_list_status("[]")[1] == "ok" and parse_list_status("tidak ada json")[1] == "failed"


def test_parse_list_memperbaiki_item_berkurung_kurawal():
    # Bentuk keluaran qwen3:8b untuk conv-26 sesi 4 (19 Okt): tiap item dibungkus {"..."}.
    reply = '[{"Caroline received a necklace from her grandma in Sweden."},{"Melanie went camping."}]'
    items, status = parse_list_status(reply)
    assert status == "repaired"
    assert items == ["Caroline received a necklace from her grandma in Sweden.", "Melanie went camping."]
    # Objek JSON sungguhan ({"key": "value"}): nilai teksnya diambil, bukan dibuang.
    assert parse_list_status('[{"fact": "A."}]') == (["A."], "ok")


def test_parse_list_salvage_json_rusak():
    # Bentuk nyata qwen3:8b conv-26 sesi 3 & 7 (19 Okt): kurawal penutup hilang, kutip di dalam kalimat tak di-escape.
    reply = '[{"Caroline is thankful."},{"Caroline likes the book "Becoming Nicole" a lot."},{"Family is everything."]'
    items, status = parse_list_status(reply)
    assert status == "salvaged"
    assert items == ["Caroline is thankful.", 'Caroline likes the book "Becoming Nicole" a lot.', "Family is everything."]


def test_parse_list_beberapa_daftar_per_baris():
    # Bentuk nyata olmo-3:7b-instruct (19 Okt): satu daftar per baris, ada daftar kosong.
    reply = '["Jon lost his job as a banker."]  \n[]\n["Gina\'s favorite dance style is contemporary"]  \n["Jon won."]\n[]'
    items, status = parse_list_status(reply)
    assert status == "repaired"
    assert items == ["Jon lost his job as a banker.", "Gina's favorite dance style is contemporary", "Jon won."]


def test_parse_list_jawaban_terpotong():
    # Bentuk nyata qwen3:8b (19 Okt): berputar sampai batas 1024 token, terpotong di tengah item.
    reply = '[{"Audrey has four dogs."},{"Pets bring comfort."},{"Pets bring comfort."},{"Aud'
    items, status = parse_list_status(reply)
    assert status == "truncated" and items == ["Audrey has four dogs.", "Pets bring comfort."]


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
