"""
locomo.py — Minggu 2: membaca percakapan LoCoMo per sesi dan menyisipkan racun.

Alur:
  load_sessions("conv-26")          -> daftar sesi: tanggal, turn dialog, halaman eksternal (awalnya kosong)
  inject_poison(sessions, case)     -> salinan sesi dengan racun di inject_session (A1/A2 turn, A3/eksternal halaman)
  writer_chunks(sessions)           -> potongan teks yang dibaca memory_writer, masing-masing dengan `source`

Kenapa `source` ditentukan di sini, bukan oleh LLM?
  Asal-usul teks (dialog vs halaman eksternal) diketahui dari STRUKTUR data. Gate nanti membaca field ini.

PENTING: field `observation`, `session_summary`, dan `event_summary` di LoCoMo adalah memori yang sudah
diringkas pembuat dataset. TIDAK dipakai: kalau dipakai, memori masuk tanpa lewat memory_writer dan gate.

Uji cepat: python src/locomo.py
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
    """Kembalikan list sesi berurutan. Turn hanya berisi speaker, dia_id, text (caption gambar diabaikan)."""
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
    """Teks yang terlihat di halaman HTML (seperti yang 'dibaca' agen), tanpa tag dan meta."""
    p = _TextOnly()
    p.feed((ROOT / path).read_text(encoding="utf-8"))
    return "\n".join(p.parts)


def inject_poison(sessions, case):
    """Salinan `sessions` dengan isi `case` disisipkan ke case['inject_session'].

    Berlaku untuk kasus racun (A1/A2/A3), memori eksternal bersih, dan skenario A3-auth.
    Label kasus (attack, poison_keys, dst.) TIDAK ikut disisipkan; writer hanya melihat teksnya.
    """
    out = copy.deepcopy(sessions)
    target = next((s for s in out if s["session"] == case["inject_session"]), None)
    if target is None or target["sample_id"] != case["sample_id"]:
        raise ValueError(f"{case['case_id']}: sesi {case['inject_session']} tidak ada di {case['sample_id']}")
    if case["channel"] == "dialog_turn":
        target["turns"].append(dict(case["turn"]))  # di akhir sesi
    elif case["channel"] == "external_page":
        target["pages"].append({"page_id": Path(case["page_path"]).stem, "text": page_text(case["page_path"])})
    else:
        raise ValueError(f"channel tidak dikenal: {case['channel']}")
    return out


def writer_chunks(sessions):
    """Potong sesi menjadi input memory_writer: 1 chunk dialog per sesi + 1 chunk per halaman eksternal."""
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
    print(f"conv-26: {len(sessions)} sesi, {sum(len(s['turns']) for s in sessions)} turn")
    for case in cases[:3]:  # T01: A1, A2, A3
        chunks = writer_chunks(inject_poison(sessions, case))
        changed = [c for c in chunks if c["session"] == case["inject_session"]]
        print(f"\n[{case['case_id']}] sesi {case['inject_session']}: {len(changed)} chunk")
        for c in changed:
            print(f"  {c['chunk_id']} (source={c['source']}) ... {c['text'][-110:]!r}")
