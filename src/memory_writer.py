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
from collections import Counter

from llm import load_prompt

PROMPT = load_prompt("memory_writer")


# Berapa kali jawaban writer terbaca: "ok", "repaired", "salvaged", "truncated", "failed" (= memori sesi itu kosong). Dilaporkan per model.
PARSE_STATS = Counter()


def parse_list_status(reply):
    """Ambil JSON list of string dari jawaban LLM -> (items, status).

    Toleran terhadap ```json ... ``` dan teks di sekitarnya. Dua kerusakan format yang terlihat pada model nyata
    diperbaiki (isi tidak diubah, status = "repaired"):
      - koma antar-item hilang: ["A." "B."]            (olmo-3, quicktest 15 Okt)
      - tiap item dibungkus kurung kurawal: [{"A."}, {"B."}]  (qwen3:8b, 8 dari 19 sesi conv-26, 19 Okt)
      - satu daftar per baris: ["A."]\n["B."]\n[]           (olmo-3, 19 Okt; dulu tergabung jadi 1 catatan raksasa)
    """
    m = re.search(r"\[.*\]", reply, re.S)
    if not m and reply.lstrip().startswith("[") and '"' in reply:
        # Jawaban terpotong (model berputar sampai batas NUM_PREDICT, mis. qwen3): ambil item yang sudah lengkap,
        # buang sisa yang terpotong, tutup daftarnya, dan hapus duplikat persis hasil putaran.
        cut = max(reply.rfind('"}'), reply.rfind('",'))
        if cut > 0:
            items, _ = parse_list_status(reply[:cut + (2 if reply[cut:cut + 2] == '"}' else 1)] + "]")
            return list(dict.fromkeys(items)), "truncated"
    if not m:
        return [], ("ok" if reply.strip() in ("", "[]") else "failed")
    text = m.group(0)
    repaired = re.sub(r'\{\s*("(?:[^"\\]|\\.)*")\s*\}', r"\1", text)  # {"A."} -> "A."
    repaired = re.sub(r'"\s*\n?\s*"', '", "', repaired)                 # "A." "B." -> "A.", "B."
    repaired = re.sub(r"\]\s*\[", ", ", repaired)                      # ["A."]\n["B."] -> ["A.", "B."]  (olmo-3)
    repaired = re.sub(r",\s*(?=,|\])", "", repaired)                    # sisa koma dari daftar kosong []
    repaired = re.sub(r"\[\s*,", "[", repaired)
    for status, candidate in (("ok", text), ("repaired", repaired)):
        try:
            items = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(items, list):
            # Item berupa objek ({"fact": "A."}) -> ambil nilai teksnya, supaya catatan tidak terbuang diam-diam.
            flat = [v for it in items for v in ([it] if isinstance(it, str) else
                                                 [x for x in it.values() if isinstance(x, str)] if isinstance(it, dict) else [])]
            return [x.strip() for x in flat if x.strip()], status
    # Cadangan terakhir ("salvaged"): JSON tetap rusak (mis. kurung kurawal penutup hilang, atau tanda kutip
    # di dalam kalimat tidak di-escape: "... the book "Becoming Nicole" ..."). Potong di batas antar-item.
    inner = re.sub(r'^\[\s*\{?\s*"|"\s*\}?\s*\]$', "", text.strip())
    if inner != text.strip():
        items = [x.strip() for x in re.split(r'"\s*\}?\s*,\s*\{?\s*"', inner) if x.strip()]
        if items:
            return items, "salvaged"
    return [], "failed"


def parse_list(reply):
    return parse_list_status(reply)[0]


def write_memories(chunk, llm):
    """Satu chunk -> list kandidat memori (dict)."""
    reply = llm.invoke(PROMPT.format(date=chunk["date"], text=chunk["text"])).content
    facts, status = parse_list_status(reply)
    PARSE_STATS[status] += 1
    return [{
        "candidate_id": f"{chunk['chunk_id']}-M{i}",
        "content": fact,
        "source": chunk["source"],
        "timestamp": chunk["date"],
        "sample_id": chunk["sample_id"],
        "session": chunk["session"],
        "chunk_id": chunk["chunk_id"],
    } for i, fact in enumerate(facts)]


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
