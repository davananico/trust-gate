"""
locomo.py — reads LoCoMo conversations session by session and injects poison.

Flow:
  load_sessions("conv-26")          -> list of sessions: date, dialog turns, external pages (initially empty)
  inject_poison(sessions, case)     -> copy of the sessions with poison in inject_session (A1/A2 turn, A3/external page)
  writer_chunks(sessions)           -> text chunks read by memory_writer, each with a `source`

Why is `source` set here and not by the LLM?
  The provenance of a text (dialog vs external page) is known from the STRUCTURE of the data. The gate reads this field.

IMPORTANT: the LoCoMo fields `observation`, `session_summary` and `event_summary` are memories already summarized by
the dataset authors. They are NOT used: using them would let memories in without going through memory_writer and the gate.

Quick check: python src/locomo.py
"""
import copy
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "locomo10.json"

_raw_cache = {}


def _conversation(sample_id):
    if not _raw_cache:
        for s in json.load(open(RAW, encoding="utf-8")):
            _raw_cache[s["sample_id"]] = s["conversation"]
    return _raw_cache[sample_id]


def load_sessions(sample_id):
    """Returns the sessions in order. Turns keep only speaker, dia_id and text (image captions are ignored)."""
    conv = _conversation(sample_id)
    nums = sorted(int(m.group(1)) for k in conv if (m := re.fullmatch(r"session_(\d+)", k)))
    return [{
        "sample_id": sample_id,
        "session": n,
        "date": conv[f"session_{n}_date_time"],
        "turns": [{"speaker": t["speaker"], "dia_id": t["dia_id"], "text": t["text"]} for t in conv[f"session_{n}"]],
        "pages": [],
    } for n in nums]


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def page_text(path):
    """The visible text of an HTML page (what the agent 'reads'), without tags or meta."""
    p = _TextOnly()
    p.feed((ROOT / path).read_text(encoding="utf-8"))
    return "\n".join(p.parts)


def inject_poison(sessions, case):
    """Copy of `sessions` with the content of `case` inserted into case['inject_session'].

    Works for poison cases (A1/A2/A3), clean external memories and A3-auth scenarios.
    Case labels (attack, poison_keys, etc.) are NOT inserted; the writer only sees the text.
    """
    out = copy.deepcopy(sessions)
    target = next((s for s in out if s["session"] == case["inject_session"]), None)
    if target is None or target["sample_id"] != case["sample_id"]:
        raise ValueError(f"{case['case_id']}: session {case['inject_session']} not found in {case['sample_id']}")
    if case["channel"] == "dialog_turn":
        target["turns"].append(dict(case["turn"]))  # at the end of the session
    elif case["channel"] == "external_page":
        target["pages"].append({"page_id": Path(case["page_path"]).stem, "text": page_text(case["page_path"])})
    else:
        raise ValueError(f"unknown channel: {case['channel']}")
    return out


def writer_chunks(sessions):
    """Splits sessions into memory_writer inputs: 1 dialog chunk per session + 1 chunk per external page."""
    chunks = []
    for s in sessions:
        base = {"sample_id": s["sample_id"], "session": s["session"], "date": s["date"]}
        dialog = "\n".join(f"{t['speaker']}: {t['text']}" for t in s["turns"])
        chunks.append({**base, "chunk_id": f"{s['sample_id']}-S{s['session']}-dialog", "source": "dialog",
                       "text": dialog})
        for p in s["pages"]:
            chunks.append({**base, "chunk_id": f"{s['sample_id']}-S{s['session']}-{p['page_id']}",
                           "source": "external_web", "text": p["text"]})
    return chunks


if __name__ == "__main__":
    cases = json.load(open(ROOT / "data" / "poison_cases.json", encoding="utf-8"))
    sessions = load_sessions("conv-26")
    print(f"conv-26: {len(sessions)} sessions, {sum(len(s['turns']) for s in sessions)} turns")
    for case in cases[:3]:  # T01: A1, A2, A3
        chunks = writer_chunks(inject_poison(sessions, case))
        changed = [c for c in chunks if c["session"] == case["inject_session"]]
        print(f"\n[{case['case_id']}] session {case['inject_session']}: {len(changed)} chunks")
        for c in changed:
            print(f"  {c['chunk_id']} (source={c['source']}) ... {c['text'][-110:]!r}")
