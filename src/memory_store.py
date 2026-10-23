"""
memory_store.py — active memory (ChromaDB) + top-k retrieval.

Retrieval settings are LOCKED here and identical for every condition:
  EMBED_MODEL  local embedding model (sentence-transformers, runs on CPU; free)
  DISTANCE     Chroma distance metric
  K            number of memories retrieved (chosen from the recall check on dev; see src/check_recall.py)

Only memories that PASS may be added here (no defense: all; with a gate: only 'accept').
Quarantined/rejected memories NEVER enter Chroma, so the agent cannot retrieve them.

Quick check: python src/memory_store.py
"""
import sqlite3
import uuid
from pathlib import Path

import numpy as np
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

ROOT = Path(__file__).resolve().parent.parent
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# bge-v1.5 recommends this prefix for QUERIES (not for memories) for more accurate search.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DISTANCE = "cosine"
K = 10  # LOCKED 19 Oct: chosen on dev with the qwen3 writer (target recall 67% @5 -> 87% @10). Same for all conditions & models.

# Candidate metadata stored with each document in Chroma.
META_KEYS = ("candidate_id", "source", "timestamp", "sample_id", "session", "chunk_id")


class LocalEmbeddings(Embeddings):
    """sentence-transformers embeddings + SQLite cache (identical text is never re-embedded)."""

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
    """One active memory for one run. Kept in RAM (not written to disk), so runs never leak into each other."""

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
        """Returns the k most similar memories: list of dicts {content, score, ...metadata}. score = distance (lower = closer)."""
        hits = self.db.similarity_search_with_score(question, k=k)
        return [{"content": d.page_content, "score": round(float(s), 4), **d.metadata} for d, s in hits]

    def count(self):
        return self.db._collection.count()


if __name__ == "__main__":
    import json

    import locomo
    from llm import FakeWriterModel
    from memory_writer import write_memories

    # Memories from the fake model = raw dialog lines. Enough to check that retrieval works.
    case = json.load(open(ROOT / "data" / "poison_cases.json", encoding="utf-8"))[0]  # T01-A1
    sessions = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
    cands = [c for ch in locomo.writer_chunks(sessions) for c in write_memories(ch, FakeWriterModel(cache=False))]
    store = MemoryStore(LocalEmbeddings())
    store.add(cands)
    print(f"{store.count()} memories stored. Question: {case['question']}")
    for h in store.retrieve(case["question"]):
        print(f"  {h['score']:.3f}  S{h['session']:<2} [{h['source']}] {h['content'][:90]}")
