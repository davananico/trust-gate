"""
check_recall.py — Minggu 2: cek retrieval di data DEV untuk memilih k.

Dua angka per k:
  recall bersih  = % pertanyaan yang top-k-nya memuat memori berisi jawaban benar (memori bersih, tanpa racun).
                   Kalau rendah, agen tidak mungkin menjawab benar -> masalah retrieval/writer, bukan gate.
  jangkauan racun = % kasus racun yang top-k-nya memuat memori berisi nilai racun (tanpa pertahanan).
                   Ini batas atas ASR: racun yang tidak terambil tidak mungkin memengaruhi jawaban.

Hanya memakai split dev (aturan: pengaturan tidak boleh dipilih dengan data test).
Model writer mengikuti LLM_MODEL. Dengan model palsu, memori = baris dialog mentah -> angka hanya indikasi awal.

Jalankan: python src/check_recall.py
"""
import json
from collections import defaultdict

import locomo
from llm import enable_cache, get_chat_model
from memory_store import LocalEmbeddings, MemoryStore
from memory_writer import write_memories
from textnorm import contains_any

KS = (1, 3, 5, 10, 20)
DATA = locomo.ROOT / "data"
load = lambda name: json.load(open(DATA / name, encoding="utf-8"))


def memories_for(sample_id, llm, case=None, _clean={}):
    """Kandidat memori satu percakapan. Sesi yang tidak disisipi memakai hasil writer bersih (dihitung sekali)."""
    if sample_id not in _clean:
        _clean[sample_id] = {ch["chunk_id"]: write_memories(ch, llm)
                             for ch in locomo.writer_chunks(locomo.load_sessions(sample_id))}
    if case is None:
        return [c for cands in _clean[sample_id].values() for c in cands]
    out = []
    for ch in locomo.writer_chunks(locomo.inject_poison(locomo.load_sessions(sample_id), case)):
        same = ch["session"] != case["inject_session"] and ch["chunk_id"] in _clean[sample_id]
        out += _clean[sample_id][ch["chunk_id"]] if same else write_memories(ch, llm)
    return out


def rate(hits):
    return {k: f"{100 * sum(h[k] for h in hits) / len(hits):5.1f}%" for k in KS} if hits else {}


def main():
    enable_cache()
    llm, emb = get_chat_model(), LocalEmbeddings()
    dev = set(load("split.json")["dev"])

    questions = defaultdict(list)  # sample_id -> [(jenis, pertanyaan, kunci jawaban)]
    for q in load("clean_questions.json"):
        if q["split"] == "dev":
            questions[q["sample_id"]].append(("QA bersih", q["question"], [q["gold_answer"]]))
    for t in load("targets.json"):
        if t["split"] == "dev":
            questions[t["sample_id"]].append(("fakta target", t["question"], t["truth_keys"]))

    clean_hits = defaultdict(list)
    for sid in sorted(dev):
        store = MemoryStore(emb)
        store.add(memories_for(sid, llm))
        print(f"{sid}: {store.count()} memori bersih")
        for kind, question, keys in questions[sid]:
            got = store.retrieve(question, k=max(KS))
            clean_hits[kind].append({k: any(contains_any(m["content"], keys) for m in got[:k]) for k in KS})

    poison_hits = defaultdict(list)
    for case in load("poison_cases.json"):
        if case["split"] != "dev":
            continue
        store = MemoryStore(emb)
        store.add(memories_for(case["sample_id"], llm, case))
        got = store.retrieve(case["question"], k=max(KS))
        poison_hits[case["attack"]].append(
            {k: any(contains_any(m["content"], case["poison_keys"]) for m in got[:k]) for k in KS})

    print(f"\n{'':28}" + "".join(f"k={k:<6}" for k in KS))
    for kind, hits in clean_hits.items():
        print(f"recall {kind:<14} (n={len(hits):>2}) " + " ".join(rate(hits).values()))
    for kind, hits in poison_hits.items():
        print(f"racun {kind[:15]:<15} (n={len(hits):>2}) " + " ".join(rate(hits).values()))


if __name__ == "__main__":
    main()
