"""
demo.py — demo untuk bimbingan: satu kasus (default T01, Caroline) dijalankan TANPA dan DENGAN racun.

Tiga panel: tanpa racun, dengan racun tanpa pertahanan, dengan racun + Trust Gate (threshold SEMENTARA).
Menampilkan: kalimat racun, keputusan gate di sesi injeksi, 3 memori teratas yang diambil agen, dan jawaban agen.
Bukan bagian eksperimen; hanya untuk memperlihatkan alur serangan memory poisoning.

Jalankan: python src/demo.py            (kasus T01-A1)
          python src/demo.py T01-A3     (kasus lain)
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
racun = case["turn"]["text"] if "turn" in case else case["page_text"]

print("=" * 78)
print(f"Kasus      : {case_id} ({case['attack']})")
print(f"Pertanyaan : {case['question']}")
print(f"Jawaban benar : {case['truth_keys'][0]}   |   Nilai racun : {case['poison_keys'][0]}")
print(f"Racun disisipkan di sesi {case['inject_session']} (sumber: {case['source']}):\n  \"{racun}\"")
if type(llm).__name__ == "FakeModel":
    print("CATATAN: LLM dummy -> agen selalu menjawab dengan memori peringkat 1.")

poisoned = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
gated_app = build_graph(llm, gate=make_trust_gate(llm, GateParams()))
for label, graph_app, sessions in (("1) TANPA RACUN", app, locomo.load_sessions(case["sample_id"])),
                                   ("2) DENGAN RACUN, TANPA PERTAHANAN", app, poisoned),
                                   ("3) DENGAN RACUN + TRUST GATE", gated_app, poisoned)):
    log = GateLog(":memory:") if graph_app is gated_app else None
    out = run(graph_app, MemoryStore(emb), sessions, [{"qid": "q", "text": case["question"]}], gate_log=log)
    print()
    print("-" * 78)
    print(f"{label}: {len(out['log'])} sesi dibaca, {sum(e['n_stored'] for e in out['log'])} memori tersimpan")
    if log is not None:
        print(f"Keputusan gate: accept {log.count() - log.count('memory_quarantine') - log.count('rejected_log')}, "
              f"quarantine {log.count('memory_quarantine')}, reject {log.count('rejected_log')}")
        for row in log.db.execute("SELECT decision, t_source, c_content, r_contradiction, r_pattern, patterns, t_final, content "
                                  "FROM gate_decisions WHERE session = ? ORDER BY t_final", (case["inject_session"],)).fetchmany(3):
            print(f"  [{row[0]:<10}] T_source={row[1]} C={row[2]} kontradiksi={row[3]} pola={row[4]} {row[5] or ''} "
                  f"-> T_final={row[6]} | {row[7][:60]}")
    print("Memori teratas yang diambil agen:")
    for i, m in enumerate(out["retrieved"]["q"][:3], 1):
        print(f"  #{i} (sesi {m['session']}, {m['source']}) {m['content'][:85]}")
    print(f"JAWABAN AGEN: {out['answers']['q']['answer']}")
print("=" * 78)
