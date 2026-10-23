"""
textnorm.py — text normalization for comparing answers.

normalize("The 'Guinea Pig'!")  -> "guinea pig"
Steps: lowercase, remove punctuation, remove articles (a, an, the), collapse whitespace.
"""
import re
import string

_PUNCT = str.maketrans({c: " " for c in string.punctuation + "‘’“”–—"})


def normalize(text):
    text = str(text).lower().translate(_PUNCT)
    return " ".join(w for w in text.split() if w not in {"a", "an", "the"})


def contains_any(text, keys):
    """True if any key (after normalization) appears as a whole word/phrase in text."""
    t = f" {normalize(text)} "
    return any(f" {normalize(k)} " in t for k in keys if normalize(k))
