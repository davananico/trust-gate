"""Tes kunci cache LLM (tanpa server). Jalankan: pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from llm import get_chat_model  # noqa: E402


def test_model_berbeda_tidak_berbagi_cache():
    # Bug 19 Okt: kunci cache ChatOllama bawaan tidak memuat nama model -> llama/olmo/gemma memakai jawaban qwen3.
    a = get_chat_model("ollama:qwen3:8b")._get_llm_string()
    b = get_chat_model("ollama:llama3.1:8b")._get_llm_string()
    assert a != b and "qwen3:8b" in a and "llama3.1:8b" in b


def test_pengaturan_masuk_kunci_cache():
    m = get_chat_model("ollama:qwen3:8b")
    key = m._get_llm_string()
    assert '"num_ctx": 8192' in key and '"temperature": 0' in key and '"reasoning": false' in key
    m.num_ctx = 4096
    assert m._get_llm_string() != key
