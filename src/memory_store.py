"""
memory_store.py — Minggu 2: memori aktif (ChromaDB) + retrieval top-k.

Pengaturan retrieval DIKUNCI di sini dan sama untuk semua kondisi (aturan CLAUDE.md no. 2):
  EMBED_MODEL  model embedding lokal (sentence-transformers, jalan di CPU; gratis)
  DISTANCE     metrik jarak Chroma
  K            jumlah memori yang diambil (dipilih dari cek recall di dev; lihat src/check_recall.py)

Hanya memori yang LOLOS (tanpa pertahanan: semua; dengan gate: hanya 'accept') yang boleh di-add ke sini.
Memori quarantine/reject TIDAK pernah masuk Chroma, jadi agen tidak bisa mengambilnya.

Uji cepat: python src/memory_store.py
"""
import sqlite3
import uuid
from pathlib import Path

import numpy as np
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

ROOT = Path(__file__).resolve().parent.parent
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# bge-v1.5 menyarankan awalan ini untuk QUERY (bukan untuk memori) agar pencarian lebih akurat.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DISTANCE = "cosine"
K = 5  # SEMENTARA. Dikunci setelah cek recall di dev.

# Metadata kandidat yang disimpan bersama dokumen di Chroma.
META_KEYS = ("candidate_id", "source", "timestamp", "sample_id", "session", "chunk_id")


class LocalEmbeddings(Embeddings):
    """Embedding sentence-transformers + cache SQLite (teks yang sama tidak dihitung ulang)."""

    def __init__(self, model_name=EMBED_MODEL, cache_path=ROOT / "cache" / "embeddings.sqlite"):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device="cpu")
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(cache_path))
        self.db.execute("CREATE TABLE IF NOT EXISTS emb (model TEXT, text TEXT, vec BLOB, PRIMARY KEY (model, text))")

    def _embed(self, texts):
        found = {}
        for t in set(texts):
            row = self.db.execute("SELECT vec FROM emb WHERE model=? AND text=?", (self.model_name, t)).fetchone()
            if row:
                found[t] = np.frombuffer(row[0], dtype=np.float32)
        missing = sorted(set(texts) - set(found))
        if missing:
            vecs = self.model.encode(missing, normalize_embeddings=True, batch_size=64).astype(np.float32)
            self.db.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?, ?)",
                                [(self.model_name, t, v.tobytes()) for t, v in zip(missing, vecs)])
            self.db.commit()
            found.update(zip(missing, vecs))
        return [found[t].tolist() for t in texts]

    def embed_documents(self, texts):
        return self._embed(list(texts))

    def embed_query(self, text):
        return self._embed([QUERY_PREFIX + text])[0]


class MemoryStore:
    """Satu memori aktif untuk satu run. Disimpan di RAM (tidak ditulis ke disk), jadi run tidak saling bocor."""

    def __init__(self, embeddings):
        self.db = Chroma(collection_name=f"run-{uuid.uuid4().hex[:8]}", embedding_function=embeddings,
                         collection_metadata={"hnsw:space": DISTANCE})

    def add(self, candidates):
        if not candidates:
            return
        self.db.add_texts([c["content"] for c in candidates],
                          metadatas=[{k: c[k] for k in META_KEYS} for c in candidates],
                          ids=[c["candidate_id"] for c in candidates])

    def retrieve(self, question, k=K):
        """Kembalikan k memori paling mirip: list dict {content, score, ...metadata}. score = jarak (kecil = mirip)."""
        hits = self.db.similarity_search_with_score(question, k=k)
        return [{"content": d.page_content, "score": round(float(s), 4), **d.metadata} for d, s in hits]

    def count(self):
        return self.db._collection.count()


if __name__ == "__main__":
    import json

    import locomo
    from llm import FakeWriterModel
    from memory_writer import write_memories

    # Memori dari model palsu = baris dialog mentah. Cukup untuk mengecek bahwa retrieval bekerja.
    case = json.load(open(ROOT / "data" / "poison_cases.json", encoding="utf-8"))[0]  # T01-A1
    sessions = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
    cands = [c for ch in locomo.writer_chunks(sessions) for c in write_memories(ch, FakeWriterModel(cache=False))]
    store = MemoryStore(LocalEmbeddings())
    store.add(cands)
    print(f"{store.count()} memori disimpan. Pertanyaan: {case['question']}")
    for h in store.retrieve(case["question"]):
        print(f"  {h['score']:.3f}  S{h['session']:<2} [{h['source']}] {h['content'][:90]}")
