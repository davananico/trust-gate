"""
gate/llm_signals.py — Minggu 3, langkah 2: dua sinyal Trust Gate yang memakai LLM.

content_confidence()  C_content (0–1): seberapa kuat kandidat didukung TEKS ASALNYA (turn asal +/- 1 baris).
contradiction()       sinyal R_poison (a): 1 jika kandidat bertentangan dengan memori aktif yang paling mirip, 0 jika tidak.

Prompt tetap di prompts/gate_confidence.txt dan prompts/gate_contradiction.txt. Sumber (dialog/eksternal) TIDAK
disebut di prompt: sumber sudah dinilai terpisah oleh tabel source trust. Jawaban yang tidak terbaca dicatat
(PARSE_STATS) dan diberi nilai netral, bukan dibuang diam-diam.
"""
import re
from collections import Counter

from gate.scoring import _tokens
from llm import load_prompt

PROMPT_CONF = load_prompt("gate_confidence")
PROMPT_CONTRA = load_prompt("gate_contradiction")
N_NEIGHBORS = 5          # memori aktif paling mirip yang dibandingkan pada cek kontradiksi
CONTEXT_WIDTH = 1        # jumlah baris di sekitar turn asal yang ikut diberikan ke LLM
NEUTRAL_CONF = 0.5       # dipakai jika jawaban confidence tidak terbaca
PARSE_STATS = Counter()  # "conf_ok", "conf_failed", "contra_ok", "contra_failed"


def context_window(candidate, chunk_text, width=CONTEXT_WIDTH):
    """Turn asal kandidat (overlap kata terbanyak) beserta `width` baris sebelum dan sesudahnya."""
    cand = _tokens(candidate)
    lines = [ln for ln in chunk_text.splitlines() if ln.strip()]
    if not lines or not cand:
        return chunk_text
    best = max(range(len(lines)), key=lambda i: (len(cand & _tokens(lines[i])) / len(cand), -len(lines[i])))
    return "\n".join(lines[max(0, best - width): best + width + 1])


def parse_confidence(reply):
    """'8' -> 0.8, '7/10' -> 0.7, '0.6' -> 0.6. None jika tidak ada angka yang masuk akal."""
    m = re.search(r"\d+(?:\.\d+)?", reply)
    if not m:
        return None
    x = float(m.group(0))
    if x <= 1 and "." in m.group(0):
        return x
    return x / 10 if 0 <= x <= 10 else None


def parse_yes_no(reply):
    m = re.search(r"\b(yes|no)\b", reply, re.I)
    return None if not m else (1.0 if m.group(1).lower() == "yes" else 0.0)


def content_confidence(candidate, chunk_text, llm):
    reply = llm.invoke(PROMPT_CONF.format(context=context_window(candidate, chunk_text), candidate=candidate)).content
    score = parse_confidence(reply)
    PARSE_STATS["conf_ok" if score is not None else "conf_failed"] += 1
    return NEUTRAL_CONF if score is None else score


def contradiction(candidate, neighbors, llm):
    """neighbors = isi memori aktif yang paling mirip (list teks). Tanpa memori aktif -> 0 tanpa memanggil LLM."""
    if not neighbors:
        return 0.0
    existing = "\n".join(f"- {n}" for n in neighbors[:N_NEIGHBORS])
    reply = llm.invoke(PROMPT_CONTRA.format(existing=existing, candidate=candidate)).content
    score = parse_yes_no(reply)
    PARSE_STATS["contra_ok" if score is not None else "contra_failed"] += 1
    return 0.0 if score is None else score
