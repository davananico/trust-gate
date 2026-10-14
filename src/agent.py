"""
agent.py — Minggu 2: agen yang memakai memori terambil.

answer_question(): menjawab pertanyaan hanya dari memori (untuk clean accuracy, ASR A1–A3, DCR).
act_on_request():  menanggapi permintaan user dengan akses ke tool send_file (untuk A3-auth).
                   Setiap usulan send_file dari LLM DICATAT lewat tools.send_file() (tool palsu, tidak mengirim apa pun).

Prompt agen sengaja netral: tidak menyuruh mematuhi memori dan tidak menyuruh menolak.
Pertahanan hanya boleh datang dari gate, supaya perbandingan kondisi adil.
"""
import tools
from llm import load_prompt

PROMPT_QA = load_prompt("agent_answer")
PROMPT_TOOL = load_prompt("agent_tool")


def format_memories(memories):
    """Memori terambil -> teks untuk prompt. Urutan = peringkat retrieval. Sumber TIDAK ditampilkan ke agen."""
    return "\n".join(f"- ({m['timestamp']}) {m['content']}" for m in memories)


def answer_question(question, memories, llm):
    return llm.invoke(PROMPT_QA.format(memories=format_memories(memories), question=question)).content.strip()


def act_on_request(request, memories, llm, run_id="", case_id=""):
    """Kembalikan (teks jawaban, list tool call yang DIUSULKAN + hasil cek allowlist)."""
    msg = llm.bind_tools([tools.send_file_schema]).invoke(
        PROMPT_TOOL.format(memories=format_memories(memories), request=request))
    calls = []
    for tc in msg.tool_calls:
        args = tc.get("args", {})
        entry = {"name": tc["name"], "path": str(args.get("path", "")), "destination": str(args.get("destination", ""))}
        if tc["name"] == "send_file":
            entry["result"] = tools.send_file(entry["path"], entry["destination"], run_id=run_id, case_id=case_id)["status"]
        calls.append(entry)
    return str(msg.content).strip(), calls
