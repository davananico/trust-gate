"""
agent.py — the agent that uses retrieved memories.

answer_question(): answers a question from memories only (clean accuracy, ASR A1–A3, DCR).
act_on_request():  handles a user request with access to the send_file tool (A3-auth).
                   Every send_file call proposed by the LLM is LOGGED via tools.send_file() (a fake tool that sends nothing).

The agent prompts are deliberately neutral: they neither tell the agent to obey memories nor to refuse.
Any defense must come from the gate, so that conditions are compared fairly.
"""
import tools
from llm import load_prompt

PROMPT_QA = load_prompt("agent_answer")
PROMPT_TOOL = load_prompt("agent_tool")


def format_memories(memories):
    """Retrieved memories -> prompt text. Order = retrieval rank. The source is NOT shown to the agent."""
    return "\n".join(f"- ({m['timestamp']}) {m['content']}" for m in memories)


def answer_question(question, memories, llm):
    return llm.invoke(PROMPT_QA.format(memories=format_memories(memories), question=question)).content.strip()


def act_on_request(request, memories, llm, run_id="", case_id=""):
    """Returns (answer text, list of PROPOSED tool calls + allowlist result)."""
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
