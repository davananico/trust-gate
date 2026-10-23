"""
graph.py — the agent pipeline as a LangGraph graph.

No defense:

  START ─► memory_writer ─► store ─┬─(sessions left)─► memory_writer
                                   └─(all sessions done)─► retrieve ─► agent_answer ─► END

With the Trust Gate only ONE edge changes: memory_writer ─► trust_gate ─► store.
All other node functions are shared, so both graphs are built from the same code.

Sessions are processed one at a time in chronological order, so the gate can check each candidate against the
memories ALREADY stored from earlier sessions.

Long-term memory = a MemoryStore (Chroma) created fresh for every run. LangGraph's built-in memory/checkpointer
features are NOT used.
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
    sessions: list     # conversation sessions (already poisoned in attack conditions)
    idx: int           # index of the session being processed
    store: object      # MemoryStore for this run
    gate_log: object   # GateLog (SQLite) for gated runs; None without a gate
    candidates: list   # memory candidates from the session being processed
    log: list          # per session: number of candidates and number stored
    mode: str          # "qa" (answer questions) or "tool" (a request that may trigger send_file)
    queries: list      # [{"qid": ..., "text": ...}]
    retrieved: dict    # qid -> retrieved memories
    answers: dict      # qid -> {"answer": ..., "tool_calls": [...]}


def build_graph(llm, gate=None):
    """gate=None -> no defense. With a gate: gate = gate.trust_gate.make_trust_gate(llm, params)."""

    def memory_writer(state):
        session = state["sessions"][state["idx"]]
        # _chunk_text: the candidate's source text, needed by the gate (patterns + confidence). Not stored in Chroma.
        cands = [{**c, "_chunk_text": ch["text"]} for ch in locomo.writer_chunks([session]) for c in write_memories(ch, llm)]
        return {"candidates": cands}

    def store(state):
        # No gate: every candidate is stored. With a gate: only those with decision == "accept".
        cands = state["candidates"]
        accepted = [c for c in cands if c.get("decision", "accept") == "accept"]
        state["store"].add(accepted)
        if state.get("gate_log") is not None and cands:  # quarantine/reject never enter Chroma, only SQLite
            state["gate_log"].write(cands, state.get("run_id", ""), state.get("case_id", ""))
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


def run(app, store, sessions, queries, mode="qa", run_id="", case_id="", gate_log=None):
    """Execute one run. recursion_limit is raised: each session = 2–3 steps, a conversation can have 30+ sessions."""
    return app.invoke({"run_id": run_id, "case_id": case_id, "sessions": sessions, "idx": 0, "store": store,
                       "gate_log": gate_log, "mode": mode, "queries": queries}, config={"recursion_limit": 1000})


if __name__ == "__main__":
    import json

    from llm import get_chat_model
    from memory_store import LocalEmbeddings, MemoryStore

    case = json.load(open(locomo.ROOT / "data" / "poison_cases.json", encoding="utf-8"))[0]  # T01-A1
    llm = get_chat_model()
    app = build_graph(llm)
    out = run(app, MemoryStore(LocalEmbeddings()), locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case),
              [{"qid": case["target_id"], "text": case["question"]}], case_id=case["case_id"])
    print(f"{len(out['log'])} sessions processed, {sum(e['n_stored'] for e in out['log'])} memories stored")
    print(f"Question: {case['question']}\nAnswer  : {out['answers'][case['target_id']]['answer']}")
