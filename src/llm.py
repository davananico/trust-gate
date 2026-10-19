"""
llm.py — satu tempat untuk memilih model LLM dan mengaktifkan cache.

Model dipilih dari variabel LLM_MODEL di .env, format "provider:nama-model":
  fake                  -> model palsu deterministik (tanpa internet), untuk mengetes alur
  openai:gpt-4o-mini    -> OpenAI (butuh OPENAI_API_KEY)
  ollama:<nama-model>   -> model lokal di server lab (butuh paket langchain-ollama; dipasang nanti)

Cache: setiap pasangan (prompt, model) disimpan di cache/llm_cache.sqlite. Panggilan yang sama persis
tidak memanggil model lagi -> lebih cepat, lebih murah, dan hasil bisa diulang persis.
"""
import json
import os
import re
import sqlite3
import warnings
from pathlib import Path

from dotenv import load_dotenv
from langchain_core._api import LangChainBetaWarning
from langchain_core.caches import BaseCache
from langchain_core.globals import set_llm_cache
from langchain_core.language_models import BaseChatModel
from langchain_core.load import dumps, loads
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult, Generation

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
CACHE_ALLOWED = [ChatGeneration, Generation, AIMessage]
NUM_CTX = 8192
NUM_PREDICT = 1024  # batas panjang jawaban; jawaban writer normal <= ~480 token (qwen3 sempat berputar sampai 81.920 token)
SEED = 2026


class SQLiteLLMCache(BaseCache):
    """Cache LangChain sederhana di atas sqlite3 bawaan Python."""

    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS cache (prompt TEXT, llm TEXT, value TEXT, "
                          "PRIMARY KEY (prompt, llm))")

    def lookup(self, prompt, llm_string):
        row = self.conn.execute("SELECT value FROM cache WHERE prompt=? AND llm=?", (prompt, llm_string)).fetchone()
        if not row:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", LangChainBetaWarning)
            # Hanya objek jawaban LLM yang boleh dihidupkan kembali dari cache (bukan objek model/konfigurasi).
            return loads(row[0], allowed_objects=CACHE_ALLOWED)

    def update(self, prompt, llm_string, return_val):
        self.conn.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (prompt, llm_string, dumps(return_val)))
        self.conn.commit()

    def clear(self, **kwargs):
        self.conn.execute("DELETE FROM cache")
        self.conn.commit()


class FakeModel(BaseChatModel):
    """Model palsu deterministik untuk mengetes ALUR tanpa LLM. Angka hasilnya tidak bermakna ilmiah.

    Perilaku menurut jenis prompt:
      writer (<text>...</text>)        -> setiap baris >= 4 kata jadi satu memori (writer paling naif)
      agen QA (<memories> + Question:) -> menjawab dengan isi memori PERTAMA (peringkat 1 retrieval)
      agen tool (User request:)        -> jika ada memori "... to <domain>.example", memanggil send_file ke domain itu
    """

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = messages[-1].content
        content, tool_calls = "[]", []
        writer = re.search(r"<text>\n(.*)\n</text>", prompt, re.S)
        mem = re.search(r"<memories>\n(.*?)\n</memories>", prompt, re.S)
        if writer:
            content = json.dumps([ln.strip() for ln in writer.group(1).splitlines() if len(ln.split()) >= 4])
        elif mem and "User request:" in prompt:
            dom = re.search(r"\bto ([\w-]+(?:\.[\w-]+)*\.example)\b", mem.group(1))
            if dom:
                content = ""
                tool_calls = [{"name": "send_file", "args": {"path": "personal_files", "destination": dom.group(1)},
                               "id": "call_0", "type": "tool_call"}]
            else:
                content = "Where would you like me to back up your files?"
        elif mem:
            first = mem.group(1).splitlines()[0] if mem.group(1).strip() else ""
            content = re.sub(r"^- \(.*?\) (\w+: )?", "", first) or "I don't know"
        msg = AIMessage(content=content, tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self  # model palsu sudah "tahu" tool send_file

    @property
    def _llm_type(self):
        return "fake"


FakeWriterModel = FakeModel  # nama lama


def _keyed_ollama():
    """ChatOllama yang kunci cache-nya memuat NAMA MODEL dan pengaturannya.

    Bawaan langchain-ollama 1.1.0, kunci cache hanya "chat-ollama" -> semua model berbagi cache: jawaban qwen3
    dipakai untuk llama/olmo/gemma tanpa peringatan (ketahuan 19 Okt). Jangan dihapus.
    """
    from langchain_ollama import ChatOllama

    class KeyedChatOllama(ChatOllama):
        def _get_llm_string(self, stop=None, **kwargs):
            key = {k: getattr(self, k, None) for k in ("model", "temperature", "num_ctx", "num_predict", "reasoning", "format", "seed")}
            return super()._get_llm_string(stop=stop, **kwargs) + "|" + json.dumps(key, sort_keys=True, default=str)

    return KeyedChatOllama


def get_chat_model(name=None):
    """Kembalikan chat model sesuai LLM_MODEL. Temperature 0 supaya jawaban tidak acak."""
    name = name or os.getenv("LLM_MODEL", "fake")
    if name == "fake" or (name.startswith("openai:") and not os.getenv("OPENAI_API_KEY", "").startswith("sk-")):
        if name != "fake":
            print(f"[llm] {name} butuh OPENAI_API_KEY yang valid -> pakai model palsu")
        return FakeModel(cache=False)  # model palsu tidak di-cache: kodenya bisa berubah, kunci cache tidak
    if name.startswith("ollama:"):
        # reasoning=False: mode "thinking" (qwen3, gemma4) dimatikan untuk SEMUA model, supaya cepat dan setara.
        # Alamat server: OLLAMA_HOST (default localhost:11434 = lewat terowongan SSH ke server lab).
        # num_ctx=8192 untuk SEMUA model: default Ollama 4096 dan teks yang lebih panjang dipotong DIAM-DIAM.
        # (Prompt writer terpanjang ~1.500 token, jadi 8192 memberi ruang aman.)
        return _keyed_ollama()(model=name.split(":", 1)[1], temperature=0, reasoning=False, num_ctx=NUM_CTX,
                               num_predict=NUM_PREDICT, seed=SEED,
                               base_url=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    from langchain.chat_models import init_chat_model
    return init_chat_model(name, temperature=0)


def enable_cache(path=ROOT / "cache" / "llm_cache.sqlite"):
    set_llm_cache(SQLiteLLMCache(str(path)))


def load_prompt(name):
    return (ROOT / "prompts" / f"{name}.txt").read_text(encoding="utf-8")
