"""
gate/scoring.py — Minggu 3: bagian Trust Gate yang TIDAK memakai LLM.

Rumus (CLAUDE.md §3):
  T_base  = min(T_source, C_content)
  T_time  = exp(-lambda_t * delta_t)          delta_t = umur SUMBER (hari) saat dicatat
  T_final = T_base * T_time - lambda_r * R_poison
  T_final >= theta_accept -> accept | theta_reject <= T_final < theta_accept -> quarantine | lainnya -> reject

R_poison = max(sinyal kontradiksi (LLM, langkah 2), sinyal pola (di sini)).
Semua fungsi murni: input angka/teks -> output angka/teks. Tidak membaca label serangan apa pun.

Catatan data: di eksperimen ini semua sumber bertanggal saat injeksi, jadi delta_t = 0 dan T_time = 1.
"""
import math
import re
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[2] / "config" / "source_trust.yaml"
_WORD = re.compile(r"[a-z0-9']+")
_STOP = {"the", "and", "for", "that", "this", "with", "was", "are", "has", "have", "had", "her", "his", "she", "they",
         "you", "but", "not", "from", "about", "just", "what", "been", "really", "very", "also", "its", "it's", "i'm"}


@lru_cache(maxsize=None)
def load_config(path=CONFIG):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    compiled = {cat: [re.compile(p, re.I) for p in pats] for cat, pats in cfg["patterns"].items()}
    return cfg["source_trust"], compiled


def source_trust(source):
    table, _ = load_config()
    return table.get(source, table["default"])


def pattern_hits(text):
    """Kategori pola mencurigakan yang muncul di teks, mis. ['over_assertion']. Kosong = tidak ada."""
    _, compiled = load_config()
    return sorted(cat for cat, pats in compiled.items() if any(p.search(text) for p in pats))


def _tokens(text):
    return {w for w in _WORD.findall(text.lower()) if len(w) >= 3 and w not in _STOP}


def source_span(candidate, chunk_text):
    """Baris di teks sumber yang paling mungkin melahirkan kandidat (overlap kata terbanyak).

    Dipakai supaya pola diperiksa pada turn asal kandidat saja, bukan seluruh sesi: catatan bersih dari
    sesi yang sama tidak ikut tertandai hanya karena ada turn racun di sesi itu.
    """
    cand = _tokens(candidate)
    lines = [ln for ln in chunk_text.splitlines() if ln.strip()]
    if not lines or not cand:
        return ""
    return max(lines, key=lambda ln: (len(cand & _tokens(ln)) / len(cand), -len(ln)))


def time_factor(age_days, lambda_t):
    return math.exp(-lambda_t * max(0.0, age_days))


def trust_score(t_source, c_content, r_poison, age_days=0.0, lambda_t=0.0, lambda_r=1.0):
    """T_final. Semua masukan 0–1 (kecuali umur dan bobot)."""
    return min(t_source, c_content) * time_factor(age_days, lambda_t) - lambda_r * r_poison


def decide(score, theta_accept, theta_reject):
    if theta_reject > theta_accept:
        raise ValueError("theta_reject harus <= theta_accept")
    return "accept" if score >= theta_accept else "quarantine" if score >= theta_reject else "reject"
