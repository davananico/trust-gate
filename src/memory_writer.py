"""
memory_writer.py — turns one chunk (from locomo.writer_chunks) into memory candidates.

Memory candidate = a short fact + provenance metadata. Candidates are NOT stored yet: next they pass through
trust_gate (or go straight to the store in the no-defense condition).

Metadata carried along: source and timestamp (from the chunk, not from the LLM), chunk_id (to fetch the source
text when the gate scores content confidence). Attack labels (is_poison etc.) are NOT present here;
labels are attached separately at evaluation time.

Quick check (fake model): python src/memory_writer.py
"""
import json
import re
from collections import Counter

from llm import load_prompt

PROMPT = load_prompt("memory_writer")


# How writer replies were parsed: "ok", "repaired", "salvaged", "truncated", "failed" (= that session's memory is empty). Reported per model.
PARSE_STATS = Counter()


def parse_list_status(reply):
    """Extract a JSON list of strings from an LLM reply -> (items, status).

    Tolerates ```json ... ``` and surrounding text. Format errors seen in real models are repaired
    (content is not changed, status = "repaired"):
      - missing commas between items: ["A." "B."]              (olmo-3, quicktest 15 Oct)
      - each item wrapped in curly braces: [{"A."}, {"B."}]   (qwen3:8b, 8 of 19 sessions of conv-26, 19 Oct)
      - one list per line: ["A."]\n["B."]\n[]                  (olmo-3, 19 Oct; previously merged into 1 giant memory)
    """
    m = re.search(r"\[.*\]", reply, re.S)
    if not m and reply.lstrip().startswith("[") and '"' in reply:
        # Truncated reply (model looped until the NUM_PREDICT cap, e.g. qwen3): keep the complete items,
        # drop the cut-off tail, close the list, and remove exact duplicates produced by the loop.
        cut = max(reply.rfind('"}'), reply.rfind('",'))
        if cut > 0:
            items, _ = parse_list_status(reply[:cut + (2 if reply[cut:cut + 2] == '"}' else 1)] + "]")
            return list(dict.fromkeys(items)), "truncated"
    if not m:
        return [], ("ok" if reply.strip() in ("", "[]") else "failed")
    text = m.group(0)
    repaired = re.sub(r'\{\s*("(?:[^"\\]|\\.)*")\s*\}', r"\1", text)  # {"A."} -> "A."
    repaired = re.sub(r'"\s*\n?\s*"', '", "', repaired)                 # "A." "B." -> "A.", "B."
    repaired = re.sub(r"\]\s*\[", ", ", repaired)                      # ["A."]\n["B."] -> ["A.", "B."]  (olmo-3)
    repaired = re.sub(r",\s*(?=,|\])", "", repaired)                    # leftover commas from empty lists []
    repaired = re.sub(r"\[\s*,", "[", repaired)
    for status, candidate in (("ok", text), ("repaired", repaired)):
        try:
            items = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(items, list):
            # Items that are objects ({"fact": "A."}) -> take their text values, so no memory is silently dropped.
            flat = [v for it in items for v in ([it] if isinstance(it, str) else
                                                 [x for x in it.values() if isinstance(x, str)] if isinstance(it, dict) else [])]
            return [x.strip() for x in flat if x.strip()], status
    # Last resort ("salvaged"): the JSON is still broken (e.g. a missing closing brace, or unescaped quotes
    # inside a sentence: "... the book "Becoming Nicole" ..."). Split at item boundaries.
    inner = re.sub(r'^\[\s*\{?\s*"|"\s*\}?\s*\]$', "", text.strip())
    if inner != text.strip():
        items = [x.strip() for x in re.split(r'"\s*\}?\s*,\s*\{?\s*"', inner) if x.strip()]
        if items:
            return items, "salvaged"
    return [], "failed"


def parse_list(reply):
    return parse_list_status(reply)[0]


def write_memories(chunk, llm):
    """One chunk -> list of memory candidates (dicts)."""
    reply = llm.invoke(PROMPT.format(date=chunk["date"], text=chunk["text"])).content
    facts, status = parse_list_status(reply)
    PARSE_STATS[status] += 1
    return [{
        "candidate_id": f"{chunk['chunk_id']}-M{i}",
        "content": fact,
        "source": chunk["source"],
        "timestamp": chunk["date"],
        "sample_id": chunk["sample_id"],
        "session": chunk["session"],
        "chunk_id": chunk["chunk_id"],
    } for i, fact in enumerate(facts)]


if __name__ == "__main__":
    import locomo
    from llm import enable_cache, get_chat_model

    enable_cache()
    llm = get_chat_model()
    case = json.load(open(locomo.ROOT / "data" / "poison_cases.json", encoding="utf-8"))[2]  # T01-A3
    sessions = locomo.inject_poison(locomo.load_sessions(case["sample_id"]), case)
    for chunk in locomo.writer_chunks(sessions):
        if chunk["session"] != case["inject_session"]:
            continue
        cands = write_memories(chunk, llm)
        print(f"\n{chunk['chunk_id']} (source={chunk['source']}): {len(cands)} candidates")
        for c in cands[-3:]:
            print(f"  [{c['source']}] {c['content'][:100]}")
