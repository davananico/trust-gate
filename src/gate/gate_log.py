"""
gate/gate_log.py — catatan keputusan gate di SQLite (CLAUDE.md §4).

Tabel:
  gate_decisions     SEMUA kandidat yang lewat gate + semua sinyal + keputusan (untuk threshold/ablation offline)
  memory_quarantine  kandidat 'quarantine' (disimpan terpisah, TIDAK dipakai agen)
  rejected_log       kandidat 'reject'
Label serangan TIDAK disimpan di sini; dicocokkan saat evaluasi lewat case_id + isi kandidat.
"""
import sqlite3
from pathlib import Path

COLS = ["run_id", "case_id", "candidate_id", "sample_id", "session", "source", "content", "t_source", "c_content",
        "r_contradiction", "r_pattern", "patterns", "t_final", "decision", "gate_mode"]


class GateLog:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        for table in ("gate_decisions", "memory_quarantine", "rejected_log"):
            self.db.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(COLS)})")

    def write(self, candidates, run_id="", case_id=""):
        rows = [[run_id, case_id] + [c.get(k) for k in COLS[2:]] for c in candidates]
        q = f"INSERT INTO {{}} VALUES ({', '.join('?' * len(COLS))})"
        self.db.executemany(q.format("gate_decisions"), rows)
        self.db.executemany(q.format("memory_quarantine"), [r for r, c in zip(rows, candidates) if c["decision"] == "quarantine"])
        self.db.executemany(q.format("rejected_log"), [r for r, c in zip(rows, candidates) if c["decision"] == "reject"])
        self.db.commit()

    def count(self, table="gate_decisions"):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
