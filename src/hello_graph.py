"""
hello_graph.py — latihan LangGraph Minggu 1: graph 3 node yang memanggil LLM.

Bukan bagian eksperimen. Tujuannya hanya memastikan LangChain, LangGraph, dan Chroma
terpasang dan kamu paham tiga konsep dasarnya:

  State   = "papan tulis" bersama yang dibaca dan ditulis setiap node (di sini: dict TypedDict).
  Node    = satu langkah kerja (fungsi Python biasa) yang menerima state dan mengembalikan perubahan.
  Edge    = panah antar-node. Conditional edge = panah yang tujuannya dipilih oleh sebuah fungsi.

Alur graph:

  write_memory ──(ada fakta?)──► store ──► answer ──► END
        │
        └──(tidak ada fakta)──► END

Cara menjalankan (dari folder proyek, venv aktif):
  python src/hello_graph.py            # pakai model asli jika .env berisi kunci API
  LLM_MODEL=fake python src/hello_graph.py   # tanpa API: model palsu, untuk cek instalasi
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
    """Kembalikan (chat_model, embedding). Mode 'fake' tidak memanggil internet."""
    if MODEL == "fake" or not os.getenv("OPENAI_API_KEY"):
        from langchain_core.embeddings import DeterministicFakeEmbedding
        from langchain_core.language_models import FakeListChatModel
        print("[mode fake] tidak ada kunci API -> pakai model palsu (jawaban sudah ditentukan)")
        llm = FakeListChatModel(responses=["Caroline's grandmother is from Sweden.", "Sweden."])
        return llm, DeterministicFakeEmbedding(size=64)
    from langchain.chat_models import init_chat_model
    from langchain_openai import OpenAIEmbeddings
    llm = init_chat_model(MODEL, temperature=0)  # temperature 0 = jawaban tidak acak
    return llm, OpenAIEmbeddings(model=EMBED)


llm, embeddings = make_models()
store = Chroma(collection_name="hello", embedding_function=embeddings)  # di memori, tidak ditulis ke disk


class State(TypedDict, total=False):
    turn: str        # input: satu kalimat dialog
    question: str    # input: pertanyaan di sesi berikutnya
    memory: str      # diisi node write_memory
    retrieved: list  # diisi node answer
    answer: str      # diisi node answer


def write_memory(state: State) -> State:
    """Node 1 (memory writer): LLM meringkas turn jadi satu fakta pendek."""
    prompt = ("Extract one short factual memory about the speaker from this message. "
              "Reply with the fact only, or NONE if there is no fact.\n\n" + state["turn"])
    fact = llm.invoke(prompt).content.strip()
    print(f"[write_memory] {fact}")
    return {"memory": "" if fact.upper() == "NONE" else fact}


def has_memory(state: State) -> str:
    """Fungsi conditional edge: menentukan node berikutnya."""
    return "store" if state.get("memory") else END


def store_memory(state: State) -> State:
    """Node 2 (memory store): simpan fakta ke Chroma. Di eksperimen asli, Trust Gate ada SEBELUM node ini."""
    store.add_texts([state["memory"]], metadatas=[{"source": "dialog"}])
    print(f"[store] disimpan ke Chroma: {state['memory']}")
    return {}


def answer(state: State) -> State:
    """Node 3 (agen): ambil memori paling mirip, lalu LLM menjawab hanya dari memori itu."""
    docs = store.similarity_search(state["question"], k=1)
    mem = [d.page_content for d in docs]
    prompt = ("Answer the question using only these memories. Be short.\n"
              f"Memories: {mem}\nQuestion: {state['question']}")
    out = llm.invoke(prompt).content.strip()
    print(f"[answer] memori diambil: {mem} -> jawaban: {out}")
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
    print("\nState akhir:", result)
