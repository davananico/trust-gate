"""
gate/llm_signals.py — the two Trust Gate signals that use an LLM.

content_confidence()  C_content (0–1): how strongly the candidate is supported by its SOURCE TEXT (source turn +/- 1 line).
contradiction()       R_poison signal (a): 1 if the candidate conflicts with the most similar active memories, else 0.

Fixed prompts in prompts/gate_confidence.txt and prompts/gate_contradiction.txt. The source (dialog/external) is NOT
mentioned in the prompts: it is scored separately by the source-trust table. Unparseable replies are counted
(PARSE_STATS) and given a neutral value, never silently dropped.
"""
import re
from collections import Counter

from gate.scoring import _tokens
from llm import load_prompt

PROMPT_CONF = load_prompt("gate_confidence")
PROMPT_CONTRA = load_prompt("gate_contradiction")
N_NEIGHBORS = 5          # most similar active memories compared in the contradiction check
CONTEXT_WIDTH = 1        # number of lines around the source turn given to the LLM
NEUTRAL_CONF = 0.5       # used when a confidence reply cannot be parsed
PARSE_STATS = Counter()  # "conf_ok", "conf_failed", "contra_ok", "contra_failed"


def context_window(candidate, chunk_text, width=CONTEXT_WIDTH):
    """The candidate's source turn (largest word overlap) plus `width` lines before and after it."""
    cand = _tokens(candidate)
    lines = [ln for ln in chunk_text.splitlines() if ln.strip()]
    if not lines or not cand:
        return chunk_text
    best = max(range(len(lines)), key=lambda i: (len(cand & _tokens(lines[i])) / len(cand), -len(lines[i])))
    return "\n".join(lines[max(0, best - width): best + width + 1])


def parse_confidence(reply):
    """'8' -> 0.8, '7/10' -> 0.7, '0.6' -> 0.6. None if there is no sensible number."""
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
    """neighbors = contents of the most similar active memories (list of text). No active memory -> 0 without an LLM call."""
    if not neighbors:
        return 0.0
    existing = "\n".join(f"- {n}" for n in neighbors[:N_NEIGHBORS])
    reply = llm.invoke(PROMPT_CONTRA.format(existing=existing, candidate=candidate)).content
    score = parse_yes_no(reply)
    PARSE_STATS["contra_ok" if score is not None else "contra_failed"] += 1
    return 0.0 if score is None else score
