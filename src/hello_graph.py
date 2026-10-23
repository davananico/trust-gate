"""
hello_graph.py — LangGraph warm-up exercise: a 3-node graph that calls an LLM.

Not part of the experiment. It only checks that LangChain, LangGraph and Chroma are installed and illustrates
the three basic concepts:

  State   = a shared "whiteboard" read and written by every node (here: a TypedDict).
  Node    = one step of work (a plain Python function) that receives the state and returns updates.
  Edge    = an arrow between nodes. Conditional edge = an arrow whose target is chosen by a function.

Graph flow:

  write_memory ──(fact found?)──► store ──► answer ──► END
        │
        └──(no fact)──► END

How to run (from the project folder, venv active):
  python src/hello_graph.py            # uses the real model if .env has an API key
  LLM_MODEL=fake python src/hello_graph.py   # no API: fake model, to check the installation
"""
import os
from typing import TypedDict

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langgraph.graph import END, START, StateGraph

load_dotenv()
MODEL = os.getenv("LLM_MODEL", "openai:gpt-4o-mini")
EMBED = os.getenv("EMBED_MODEL", "text-embedding-3-small")


def make_models():
    """Returns (chat_model, embedding). 'fake' mode makes no network calls."""
    if MODEL == "fake" or not os.getenv("OPENAI_API_KEY"):
        from langchain_core.embeddings import DeterministicFakeEmbedding
        from langchain_core.language_models import FakeListChatModel
        print("[fake mode] no API key -> using a fake model (predefined answers)")
        llm = FakeListChatModel(responses=["Caroline's grandmother is from Sweden.", "Sweden."])
        return llm, DeterministicFakeEmbedding(size=64)
    from langchain.chat_models import init_chat_model
    from langchain_openai import OpenAIEmbeddings
    llm = init_chat_model(MODEL, temperature=0)  # temperature 0 = answers are not random
    return llm, OpenAIEmbeddings(model=EMBED)


llm, embeddings = make_models()
store = Chroma(collection_name="hello", embedding_function=embeddings)  # in memory, not written to disk


class State(TypedDict, total=False):
    turn: str        # input: one dialog sentence
    question: str    # input: a question in a later session
    memory: str      # filled by the write_memory node
    retrieved: list  # filled by the answer node
    answer: str      # filled by the answer node


def write_memory(state: State) -> State:
    """Node 1 (memory writer): the LLM condenses the turn into one short fact."""
    prompt = ("Extract one short factual memory about the speaker from this message. "
              "Reply with the fact only, or NONE if there is no fact.\n\n" + state["turn"])
    fact = llm.invoke(prompt).content.strip()
    print(f"[write_memory] {fact}")
    return {"memory": "" if fact.upper() == "NONE" else fact}


def has_memory(state: State) -> str:
    """Conditional-edge function: chooses the next node."""
    return "store" if state.get("memory") else END


def store_memory(state: State) -> State:
    """Node 2 (memory store): saves the fact to Chroma. In the real experiment the Trust Gate sits BEFORE this node."""
    store.add_texts([state["memory"]], metadatas=[{"source": "dialog"}])
    print(f"[store] saved to Chroma: {state['memory']}")
    return {}


def answer(state: State) -> State:
    """Node 3 (agent): retrieve the most similar memory, then the LLM answers from that memory only."""
    docs = store.similarity_search(state["question"], k=1)
    mem = [d.page_content for d in docs]
    prompt = ("Answer the question using only these memories. Be short.\n"
              f"Memories: {mem}\nQuestion: {state['question']}")
    out = llm.invoke(prompt).content.strip()
    print(f"[answer] retrieved memory: {mem} -> answer: {out}")
    return {"retrieved": mem, "answer": out}


graph = StateGraph(State)
graph.add_node("write_memory", write_memory)
graph.add_node("store", store_memory)
graph.add_node("answer", answer)
graph.add_edge(START, "write_memory")
graph.add_conditional_edges("write_memory", has_memory, ["store", END])
graph.add_edge("store", "answer")
graph.add_edge("answer", END)
app = graph.compile()

if __name__ == "__main__":
    result = app.invoke({
        "turn": "Caroline: This necklace is a gift from my grandma in my home country, Sweden.",
        "question": "What country is Caroline's grandma from?",
    })
    print("\nFinal state:", result)
