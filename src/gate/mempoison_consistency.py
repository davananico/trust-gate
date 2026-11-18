"""
gate/mempoison_consistency.py — literature baseline: the write-time consistency check of MemPoison
(Gao et al., arXiv 2607.14651; code github.com/resautu6/MemPoison, MIT, commit 7b4dd80, src/mempoison/substrates.py).

Added after the test run (18 Nov 2026, docs/post_test_changes.md). Ported line by line, without changes, including
its quirks (the token regex keeps '.', so a sentence-final word like "sweden." counts as a "special" token):

  risk = min(1, 0.45 * anchor + 0.35 * special_mismatch + 0.20 * update_hint)   max over ALL active memories
  reject if risk >= 0.58   (their default; not tuned here)

No LLM. Pure functions, tested in tests/test_mempoison_consistency.py.
"""
import re

TOKEN_RE = re.compile(r"[a-z0-9@._/-]+")
CHANGE_HINT_TOKENS = {"changed", "future", "migrate", "migrated", "move", "moved", "now", "remember", "replace",
                      "reroute", "switch", "update", "use"}
THRESHOLD = 0.58


def normalize_tokens(text):
    return set(TOKEN_RE.findall(text.lower()))


def special_tokens(text):
    return {t for t in normalize_tokens(text) if "." in t or "@" in t or "/" in t}


def consistency_conflict_score(text, records):
    """text = candidate memory; records = contents of every active memory. Same result as MemPoison's function."""
    incoming = normalize_tokens(text)
    if not records or not incoming:
        return 0.0
    incoming_special = special_tokens(text)
    update_hint = 1.0 if incoming & CHANGE_HINT_TOKENS else 0.0
    best = 0.0
    for rec in records:
        existing = normalize_tokens(rec)
        shared = incoming & existing
        if not existing or not shared:
            continue
        existing_special = special_tokens(rec)
        anchor = len(shared) / max(min(len(incoming), len(existing)), 1)
        mismatch = 1.0 if incoming_special and existing_special and incoming_special.isdisjoint(existing_special) else 0.0
        best = max(best, min(1.0, 0.45 * anchor + 0.35 * mismatch + 0.2 * update_hint))
    return round(best, 4)
