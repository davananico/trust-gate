"""
check_recall.py — retrieval check on DEV data, used to choose k.

Two numbers per k:
  clean recall  = % of questions whose top-k contains a memory with the correct answer (clean memory, no poison).
                  If this is low, the agent cannot answer correctly -> a retrieval/writer problem, not a gate problem.
  poison reach  = % of poison cases whose top-k contains a memory with the poison value (no defense).
                  This is an upper bound on ASR: poison that is never retrieved cannot affect the answer.

Uses the dev split only (rule: settings must never be chosen on test data).
The writer model follows LLM_MODEL. With the fake model, memories = raw dialog lines -> numbers are only indicative.

Run: python src/check_recall.py
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
    """Memory candidates for one conversation. Sessions without poison reuse the clean writer output (computed once)."""
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

    questions = defaultdict(list)  # sample_id -> [(kind, question, answer keys)]
    for q in load("clean_questions.json"):
        if q["split"] == "dev":
            questions[q["sample_id"]].append(("clean QA", q["question"], [q["gold_answer"]]))
    for t in load("targets.json"):
        if t["split"] == "dev":
            questions[t["sample_id"]].append(("target fact", t["question"], t["truth_keys"]))

    clean_hits = defaultdict(list)
    for sid in sorted(dev):
        store = MemoryStore(emb)
        store.add(memories_for(sid, llm))
        print(f"{sid}: {store.count()} clean memories")
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
        print(f"poison {kind[:14]:<14} (n={len(hits):>2}) " + " ".join(rate(hits).values()))


if __name__ == "__main__":
    main()
