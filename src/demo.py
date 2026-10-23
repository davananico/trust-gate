"""
demo.py — walkthrough demo: one case (default T01, Caroline) run WITHOUT and WITH poison.

Three panels: no poison, poison without defense, poison + Trust Gate (placeholder thresholds from GateParams()).
Shows: the poison sentence, gate decisions in the injection session, the top 3 memories retrieved, and the answer.
Not part of the experiment; only illustrates the memory-poisoning flow.

Run: python src/demo.py            (case T01-A1)
     python src/demo.py T01-A3     (another case)
"""
import json
import sys

import locomo
from gate.gate_log import GateLog
from gate.trust_gate import GateParams, make_trust_gate
from graph import build_graph, run
from llm import enable_cache, get_chat_model
from memory_store import LocalEmbeddings, MemoryStore

case_id = sys.argv[1] if len(sys.argv) > 1 else "T01-A1"
case = next(c for c in json.load(open(locomo.ROOT / "data" / "poison_cases.json", encoding="utf-8"))
            if c["case_id"] == case_id)
enable_cache()
llm = get_chat_model()
app, emb = build_graph(llm), LocalEmbeddings()
poison = case["turn"]["text"] if "turn" in case else case["page_text"]

print("=" * 78)
print(f"Case       : {case_id} ({case['attack']})")
print(f"Question   : {case['question']}")
print(f"True answer : {case['truth_keys'][0]}   |   Poison value : {case['poison_keys'][0]}")
print(f"Poison injected in session {case['inject_session']} (source: {case['source']}):\n  \"{poison}\"")
if type(llm).__name__ == "FakeModel":
    print("NOTE: dummy LLM -> the agent always answers with the rank-1 memory.")

poisoned = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
gated_app = build_graph(llm, gate=make_trust_gate(llm, GateParams()))
for label, graph_app, sessions in (("1) NO POISON", app, locomo.load_sessions(case["sample_id"])),
                                   ("2) POISONED, NO DEFENSE", app, poisoned),
                                   ("3) POISONED + TRUST GATE", gated_app, poisoned)):
    log = GateLog(":memory:") if graph_app is gated_app else None
    out = run(graph_app, MemoryStore(emb), sessions, [{"qid": "q", "text": case["question"]}], gate_log=log)
    print()
    print("-" * 78)
    print(f"{label}: {len(out['log'])} sessions read, {sum(e['n_stored'] for e in out['log'])} memories stored")
    if log is not None:
        print(f"Gate decisions: accept {log.count() - log.count('memory_quarantine') - log.count('rejected_log')}, "
              f"quarantine {log.count('memory_quarantine')}, reject {log.count('rejected_log')}")
        for row in log.db.execute("SELECT decision, t_source, c_content, r_contradiction, r_pattern, patterns, t_final, content "
                                  "FROM gate_decisions WHERE session = ? ORDER BY t_final", (case["inject_session"],)).fetchmany(3):
            print(f"  [{row[0]:<10}] T_source={row[1]} C={row[2]} contradiction={row[3]} pattern={row[4]} {row[5] or ''} "
                  f"-> T_final={row[6]} | {row[7][:60]}")
    print("Top memories retrieved by the agent:")
    for i, m in enumerate(out["retrieved"]["q"][:3], 1):
        print(f"  #{i} (session {m['session']}, {m['source']}) {m['content'][:85]}")
    print(f"AGENT ANSWER: {out['answers']['q']['answer']}")
print("=" * 78)
