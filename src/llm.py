"""
llm.py — one place to choose the LLM and enable the cache.

The model is chosen via the LLM_MODEL variable in .env, format "provider:model-name":
  fake                  -> deterministic fake model (no network), for testing the pipeline
  openai:gpt-4o-mini    -> OpenAI (needs OPENAI_API_KEY)
  ollama:<model-name>   -> local model on the lab server (needs the langchain-ollama package)

Cache: every (prompt, model) pair is stored in cache/llm_cache.sqlite. An identical call does not hit the model
again -> faster, cheaper, and exactly repeatable.
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
NUM_PREDICT = 1024  # reply length cap; normal writer replies are <= ~480 tokens (qwen3 once looped up to 81,920 tokens)
SEED = 2026


class SQLiteLLMCache(BaseCache):
    """A simple LangChain cache on top of Python's built-in sqlite3."""

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
            # Only LLM reply objects may be revived from the cache (never model/config objects).
            return loads(row[0], allowed_objects=CACHE_ALLOWED)

    def update(self, prompt, llm_string, return_val):
        self.conn.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (prompt, llm_string, dumps(return_val)))
        self.conn.commit()

    def clear(self, **kwargs):
        self.conn.execute("DELETE FROM cache")
        self.conn.commit()


class FakeModel(BaseChatModel):
    """Deterministic fake model for testing the PIPELINE without an LLM. Its numbers have no scientific meaning.

    Behavior by prompt type:
      writer (<text>...</text>)          -> every line with >= 4 words becomes one memory (the most naive writer)
      QA agent (<memories> + Question:)  -> answers with the FIRST memory (retrieval rank 1)
      tool agent (User request:)         -> if a memory says "... to <domain>.example", calls send_file to that domain
    """

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = messages[-1].content
        content, tool_calls = "[]", []
        writer = re.search(r"<text>\n(.*)\n</text>", prompt, re.S)
        mem = re.search(r"<memories>\n(.*?)\n</memories>", prompt, re.S)
        if "<source>" in prompt:          # gate: content confidence
            content = "9"
        elif "<existing>" in prompt:      # gate: contradiction check
            content = "NO"
        elif writer:
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
        return self  # the fake model already "knows" the send_file tool

    @property
    def _llm_type(self):
        return "fake"


FakeWriterModel = FakeModel  # old name


def _keyed_ollama():
    """ChatOllama whose cache key includes the MODEL NAME and its settings.

    In langchain-ollama 1.1.0 the default cache key is just "chat-ollama" -> all models share one cache: qwen3's
    answers were silently reused for llama/olmo/gemma (found 19 Oct). Do not remove.
    """
    from langchain_ollama import ChatOllama

    class KeyedChatOllama(ChatOllama):
        def _get_llm_string(self, stop=None, **kwargs):
            key = {k: getattr(self, k, None) for k in ("model", "temperature", "num_ctx", "num_predict", "reasoning", "format", "seed")}
            return super()._get_llm_string(stop=stop, **kwargs) + "|" + json.dumps(key, sort_keys=True, default=str)

    return KeyedChatOllama


def get_chat_model(name=None):
    """Returns the chat model for LLM_MODEL. Temperature 0 so answers are not random."""
    name = name or os.getenv("LLM_MODEL", "fake")
    if name == "fake" or (name.startswith("openai:") and not os.getenv("OPENAI_API_KEY", "").startswith("sk-")):
        if name != "fake":
            print(f"[llm] {name} needs a valid OPENAI_API_KEY -> using the fake model")
        return FakeModel(cache=False)  # the fake model is not cached: its code may change, the cache key would not
    if name.startswith("ollama:"):
        # reasoning=False: "thinking" mode (qwen3, gemma4) is turned off for ALL models, for speed and parity.
        # Server address: OLLAMA_HOST (default localhost:11434 = the lab server, directly or via an SSH tunnel).
        # num_ctx=8192 for ALL models: Ollama's default is 4096 and longer input is truncated SILENTLY.
        # (The longest writer prompt is ~1,500 tokens, so 8192 leaves a safe margin.)
        return _keyed_ollama()(model=name.split(":", 1)[1], temperature=0, reasoning=False, num_ctx=NUM_CTX,
                               num_predict=NUM_PREDICT, seed=SEED,
                               base_url=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    from langchain.chat_models import init_chat_model
    return init_chat_model(name, temperature=0)


def enable_cache(path=ROOT / "cache" / "llm_cache.sqlite"):
    set_llm_cache(SQLiteLLMCache(str(path)))


def load_prompt(name):
    return (ROOT / "prompts" / f"{name}.txt").read_text(encoding="utf-8")
