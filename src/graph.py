"""
graph.py — Minggu 2: alur agen sebagai graph LangGraph.

Tanpa pertahanan (Minggu 2):

  START ─► memory_writer ─► store ─┬─(masih ada sesi)─► memory_writer
                                   └─(semua sesi selesai)─► retrieve ─► agent_answer ─► END

Dengan Trust Gate (Minggu 3) hanya SATU edge yang berubah: memory_writer ─► trust_gate ─► store.
Fungsi node lainnya dipakai bersama (aturan CLAUDE.md no. 3).

Sesi diproses satu per satu sesuai urutan waktu, supaya di Minggu 3 gate bisa mengecek kandidat terhadap
memori yang SUDAH tersimpan dari sesi-sesi sebelumnya.

Memori jangka panjang = MemoryStore (Chroma) yang dibuat baru untuk setiap run. Fitur memori/checkpointer
bawaan LangGraph TIDAK dipakai (aturan no. 1).
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import locomo
from agent import act_on_request, answer_question
from memory_store import K
from memory_writer import write_memories


class State(TypedDict, total=False):
    run_id: str
    case_id: str
    sessions: list     # sesi percakapan (sudah disisipi racun pada kondisi serangan)
    idx: int           # indeks sesi yang sedang diproses
    store: object      # MemoryStore untuk run ini
    candidates: list   # kandidat memori dari sesi yang sedang diproses
    log: list          # per sesi: jumlah kandidat dan jumlah yang disimpan
    mode: str          # "qa" (jawab pertanyaan) atau "tool" (permintaan yang bisa memicu send_file)
    queries: list      # [{"qid": ..., "text": ...}]
    retrieved: dict    # qid -> memori terambil
    answers: dict      # qid -> {"answer": ..., "tool_calls": [...]}


def build_graph(llm, gate=None):
    """gate=None -> tanpa pertahanan. Minggu 3: gate = fungsi trust_gate."""

    def memory_writer(state):
        session = state["sessions"][state["idx"]]
        cands = [c for ch in locomo.writer_chunks([session]) for c in write_memories(ch, llm)]
        return {"candidates": cands}

    def store(state):
        # Tanpa gate: semua kandidat disimpan. Dengan gate: hanya yang decision == "accept".
        cands = state["candidates"]
        accepted = [c for c in cands if c.get("decision", "accept") == "accept"]
        state["store"].add(accepted)
        entry = {"session": state["sessions"][state["idx"]]["session"], "n_candidates": len(cands),
                 "n_stored": len(accepted)}
        return {"idx": state["idx"] + 1, "log": state.get("log", []) + [entry]}

    def more_sessions(state):
        return "memory_writer" if state["idx"] < len(state["sessions"]) else "retrieve"

    def retrieve(state):
        return {"retrieved": {q["qid"]: state["store"].retrieve(q["text"], k=K) for q in state["queries"]}}

    def agent_answer(state):
        answers = {}
        for q in state["queries"]:
            mems = state["retrieved"][q["qid"]]
            if state.get("mode", "qa") == "tool":
                text, calls = act_on_request(q["text"], mems, llm, state.get("run_id", ""), state.get("case_id", ""))
                answers[q["qid"]] = {"answer": text, "tool_calls": calls}
            else:
                answers[q["qid"]] = {"answer": answer_question(q["text"], mems, llm), "tool_calls": []}
        return {"answers": answers}

    g = StateGraph(State)
    g.add_node("memory_writer", memory_writer)
    g.add_node("store", store)
    g.add_node("retrieve", retrieve)
    g.add_node("agent_answer", agent_answer)
    g.add_edge(START, "memory_writer")
    if gate is None:
        g.add_edge("memory_writer", "store")
    else:
        g.add_node("trust_gate", lambda s: {"candidates": [gate(c, s) for c in s["candidates"]]})
        g.add_edge("memory_writer", "trust_gate")
        g.add_edge("trust_gate", "store")
    g.add_conditional_edges("store", more_sessions, ["memory_writer", "retrieve"])
    g.add_edge("retrieve", "agent_answer")
    g.add_edge("agent_answer", END)
    return g.compile()


def run(app, store, sessions, queries, mode="qa", run_id="", case_id=""):
    """Jalankan satu run. recursion_limit dinaikkan: tiap sesi = 2–3 langkah, percakapan bisa 30+ sesi."""
    return app.invoke({"run_id": run_id, "case_id": case_id, "sessions": sessions, "idx": 0, "store": store,
                       "mode": mode, "queries": queries}, config={"recursion_limit": 1000})


if __name__ == "__main__":
    import json

    from llm import get_chat_model
    from memory_store import LocalEmbeddings, MemoryStore

    case = json.load(open(locomo.ROOT / "data" / "poison_cases.json", encoding="utf-8"))[0]  # T01-A1
    llm = get_chat_model()
    app = build_graph(llm)
    out = run(app, MemoryStore(LocalEmbeddings()), locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case),
              [{"qid": case["target_id"], "text": case["question"]}], case_id=case["case_id"])
    print(f"{len(out['log'])} sesi diproses, {sum(e['n_stored'] for e in out['log'])} memori disimpan")
    print(f"Pertanyaan: {case['question']}\nJawaban  : {out['answers'][case['target_id']]['answer']}")
