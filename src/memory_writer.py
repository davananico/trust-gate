"""
memory_writer.py — Minggu 2: mengubah satu chunk (dari locomo.writer_chunks) menjadi kandidat memori.

Kandidat memori = fakta pendek + metadata asal-usul. Kandidat BELUM disimpan: berikutnya ia lewat
trust_gate (atau langsung ke store pada kondisi tanpa pertahanan).

Metadata yang ikut: source dan timestamp (dari chunk, bukan dari LLM), chunk_id (untuk mengambil teks
sumber saat gate menilai content confidence). Label serangan (is_poison dll.) TIDAK ada di sini;
label diberikan terpisah saat evaluasi.

Uji cepat (model palsu): python src/memory_writer.py
"""
import json
import re

from llm import load_prompt

PROMPT = load_prompt("memory_writer")


def parse_list(reply):
    """Ambil JSON list of string dari jawaban LLM. Toleran terhadap ```json ... ``` dan teks di sekitarnya."""
    m = re.search(r"\[.*\]", reply, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [s.strip() for s in items if isinstance(s, str) and s.strip()]


def write_memories(chunk, llm):
    """Satu chunk -> list kandidat memori (dict)."""
    reply = llm.invoke(PROMPT.format(date=chunk["date"], text=chunk["text"])).content
    return [{
        "candidate_id": f"{chunk['chunk_id']}-M{i}",
        "content": fact,
        "source": chunk["source"],
        "timestamp": chunk["date"],
        "sample_id": chunk["sample_id"],
        "session": chunk["session"],
        "chunk_id": chunk["chunk_id"],
    } for i, fact in enumerate(parse_list(reply))]


if __name__ == "__main__":
    import locomo
    from llm import enable_cache, get_chat_model

    enable_cache()
    llm = get_chat_model()
    case = json.load(open(locomo.ROOT / "data" / "poison_cases.json", encoding="utf-8"))[2]  # T01-A3
    sessions = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
    for chunk in locomo.writer_chunks(sessions):
        if chunk["session"] != case["inject_session"]:
            continue
        cands = write_memories(chunk, llm)
        print(f"\n{chunk['chunk_id']} (source={chunk['source']}): {len(cands)} kandidat")
        for c in cands[-3:]:
            print(f"  [{c['source']}] {c['content'][:100]}")
