"""
textnorm.py — normalisasi teks untuk membandingkan jawaban (CLAUDE.md §6).

normalize("The 'Guinea Pig'!")  -> "guinea pig"
Langkah: huruf kecil, hapus tanda baca, hapus artikel (a, an, the), rapikan spasi.
"""
import re
import string

_PUNCT = str.maketrans({c: " " for c in string.punctuation + "‘’“”–—"})


def normalize(text):
    text = str(text).lower().translate(_PUNCT)
    return " ".join(w for w in text.split() if w not in {"a", "an", "the"})


def contains_any(text, keys):
    """True jika salah satu kunci (setelah normalisasi) muncul sebagai kata/frasa utuh di text."""
    t = f" {normalize(text)} "
    return any(f" {normalize(k)} " in t for k in keys if normalize(k))
