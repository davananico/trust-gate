"""
gate/gate_log.py — gate decision log in SQLite.

Tables:
  gate_decisions     EVERY candidate that passes through the gate + all signals + decision (for offline threshold/ablation)
  memory_quarantine  'quarantine' candidates (stored separately, NOT used by the agent)
  rejected_log       'reject' candidates
Attack labels are NOT stored here; they are matched at evaluation time via case_id + candidate content.
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
