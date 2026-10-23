"""Tests for the LLM cache key (no server). Run: pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from llm import get_chat_model  # noqa: E402


def test_different_models_do_not_share_cache():
    # Bug found 19 Oct: the default ChatOllama cache key omits the model name -> llama/olmo/gemma reused qwen3's answers.
    a = get_chat_model("ollama:qwen3:8b")._get_llm_string()
    b = get_chat_model("ollama:llama3.1:8b")._get_llm_string()
    assert a != b and "qwen3:8b" in a and "llama3.1:8b" in b


def test_settings_are_part_of_cache_key():
    m = get_chat_model("ollama:qwen3:8b")
    key = m._get_llm_string()
    assert '"num_ctx": 8192' in key and '"temperature": 0' in key and '"reasoning": false' in key
    m.num_ctx = 4096
    assert m._get_llm_string() != key
