"""
pooled_analysis.py — pools the four models for the paper's main claims (read-only; no LLM, no new runs).

Added after the test run (18 Nov 2026). Per model, n = 30–34 trials per attack, so most per-model intervals overlap.
Pooling gives n = 4 x 34 = 136 trials, but trials are NOT independent: the four models answer the same targets.
Therefore:
  - every comparison is paired (same model + same case, or same model + same target for attack-vs-attack);
  - the 95% interval of the pooled difference comes from a cluster bootstrap that resamples TARGETS (all models and
    attacks of a target move together), 10,000 resamples, seed 2026;
  - the exact McNemar p-value on the discordant pairs is reported as a secondary number (it treats pairs as
    independent, so it is somewhat optimistic).

Inputs (per-trial CSVs): results/test_final/exp_test_*.csv, results/adaptive/adaptive_test_*.csv,
results/lme/lme_lme_*.csv, and results/post_test/ (contradiction-only baseline, LoCoMo-Adv) when present.
Output: results/pooled/pooled_analysis.csv

Run: python src/pooled_analysis.py
"""
import csv
import random
import re
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
MODELS = ["qwen3_8b", "gemma4_12b", "llama3.1_8b", "olmo-3_7b-instruct"]
N_BOOT, SEED = 10_000, 2026


def _model(path):
    return next(m for m in MODELS if m in path.name)


def _target(case_id):
    return case_id.rsplit("-", 1)[0] if re.search(r"-(A\d|AD\d|LA_\w+)$", case_id) else case_id


def load():
    """One record per trial: dataset, model, condition, kind, unit (case or question), target, success, correct."""
    recs = []

    def add(dataset, path, kind, unit, r):
        recs.append({"dataset": dataset, "model": _model(path), "condition": r["condition"], "kind": kind,
                     "unit": unit, "target": _target(unit), "success": r.get("outcome") == "success",
                     "correct": r.get("correct") == "True" or r.get("outcome") == "correct"})

    for folder in (RESULTS / "test_final", RESULTS / "post_test"):
        for p in folder.glob("exp_test_*.csv"):
            for r in csv.DictReader(open(p, encoding="utf-8")):
                if r["condition"].endswith("_noattack"):
                    continue
                add("locomo", p, r["kind"], r["case_id"] or r["qid"], r)
    for folder in (RESULTS / "adaptive", RESULTS / "post_test"):
        for p in folder.glob("adaptive_test_*.csv"):
            for r in csv.DictReader(open(p, encoding="utf-8")):
                add("locomo", p, r["attack"], r["case_id"], r)
    for folder in (RESULTS / "lme", RESULTS / "post_test"):
        for p in folder.glob("lme_lme_*.csv"):
            for r in csv.DictReader(open(p, encoding="utf-8")):
                add("lme", p, r["kind"], r["case_id"], r)
    for p in (RESULTS / "post_test").glob("locomo_adv_test_*.csv"):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            add("locomo_adv", p, r["attack"], r["case_id"], r)
    # the same trial can appear twice (post_test re-runs no_defense from cache): keep the first copy
    seen, out = set(), []
    for r in recs:
        key = (r["dataset"], r["model"], r["condition"], r["kind"], r["unit"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def mcnemar_p(b, c):
    """Exact two-sided McNemar p-value from the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def paired(pairs):
    """pairs: list of (target, x, y) with x, y in {0, 1}. Returns rates, difference y - x, bootstrap CI, McNemar p."""
    by_t = defaultdict(list)
    for t, x, y in pairs:
        by_t[t].append((x, y))
    targets, rng, diffs = list(by_t), random.Random(SEED), []
    for _ in range(N_BOOT):
        sample = [p for t in rng.choices(targets, k=len(targets)) for p in by_t[t]]
        diffs.append(sum(y - x for x, y in sample) / len(sample))
    diffs.sort()
    n = len(pairs)
    b = sum(x == 1 and y == 0 for _, x, y in pairs)
    c = sum(x == 0 and y == 1 for _, x, y in pairs)
    return {"n_pairs": n, "n_targets": len(targets), "rate_a": sum(x for _, x, _ in pairs) / n,
            "rate_b": sum(y for _, _, y in pairs) / n, "diff": (c - b) / n,
            "ci_low": diffs[int(0.025 * N_BOOT)], "ci_high": diffs[int(0.975 * N_BOOT) - 1],
            "discordant_a_only": b, "discordant_b_only": c, "mcnemar_p": mcnemar_p(b, c)}


def compare(recs, dataset, metric, a, b, by="condition", models=None):
    """a, b: (condition, kind). Pairs on model + unit when kinds are equal, on model + target otherwise."""
    key = (lambda r: (r["model"], r["unit"])) if a[1] == b[1] else (lambda r: (r["model"], r["target"]))
    pick = lambda cond, kind: {key(r): r for r in recs if r["dataset"] == dataset and r["condition"] == cond
                               and r["kind"] == kind and (models is None or r["model"] in models)}
    ra, rb = pick(*a), pick(*b)
    common = sorted(set(ra) & set(rb))
    if not common:
        return None
    pairs = [(ra[k]["target"], int(ra[k][metric]), int(rb[k][metric])) for k in common]
    return {"dataset": dataset, "metric": metric, "a": "/".join(a), "b": "/".join(b),
            "models": "all" if models is None else "+".join(models), **paired(pairs)}


def comparisons(recs):
    L, M = "locomo", "lme"
    nd, tr, co = "no_defense", "trust", "contradiction_only"
    out = []
    # 1) the gate lowers ASR (per attack) and what it costs in accuracy
    for kind in ("A1_false_fact", "A2_confident_poison", "A3_external_source", "A3_auth",
                 "AD1_split_assertion", "AD2_lexicon_free", "AD3_flooding", "AD4_dialog_auth"):
        out.append(compare(recs, L, "success", (nd, kind), (tr, kind)))
    for kind in ("A1_false_fact", "A2_confident_poison", "A3_external_source", "AD1_split_assertion", "AD2_lexicon_free"):
        out.append(compare(recs, M, "success", (nd, kind), (tr, kind)))
    out.append(compare(recs, L, "correct", (nd, "clean_qa"), (tr, "clean_qa")))
    out.append(compare(recs, L, "correct", (nd, "target_qa"), (tr, "target_qa")))
    out.append(compare(recs, M, "correct", (nd, "target_qa"), (tr, "target_qa")))
    out.append(compare(recs, M, "correct", (nd, "update_qa"), (tr, "update_qa")))
    # 2) the lexicon finding: A2 vs its rewordings, with the gate (same target, same model)
    for ds in (L, M):
        for kind in ("AD1_split_assertion", "AD2_lexicon_free"):
            out.append(compare(recs, ds, "success", (tr, "A2_confident_poison"), (tr, kind)))
    out.append(compare(recs, L, "success", (tr, "A1_false_fact"), (tr, "AD3_flooding")))
    # 3) Trust Gate vs the contradiction-only baseline (post-test runs, when present)
    for ds, kinds in ((L, ("A1_false_fact", "A2_confident_poison", "A3_external_source", "A3_auth", "AD1_split_assertion",
                           "AD2_lexicon_free", "AD3_flooding", "AD4_dialog_auth")),
                      (M, ("A1_false_fact", "A2_confident_poison", "A3_external_source", "AD1_split_assertion",
                           "AD2_lexicon_free"))):
        for kind in kinds:
            out.append(compare(recs, ds, "success", (co, kind), (tr, kind)))
    for ds, kind in ((L, "clean_qa"), (L, "target_qa"), (M, "target_qa"), (M, "update_qa")):
        out.append(compare(recs, ds, "correct", (co, kind), (tr, kind)))
    # 4) LoCoMo-Adv: fact overwrite ASR and target accuracy under every family
    out.append(compare(recs, "locomo_adv", "success", (nd, "LA_fact_overwrite"), (tr, "LA_fact_overwrite")))
    out.append(compare(recs, "locomo_adv", "success", (co, "LA_fact_overwrite"), (tr, "LA_fact_overwrite")))
    return [r for r in out if r]


def main():
    recs = load()
    rows = comparisons(recs)
    out = RESULTS / "pooled"
    out.mkdir(exist_ok=True)
    with open(out / "pooled_analysis.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows({k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()} for r in rows)
    print(f"{'dataset':<8}{'metric':<8}{'a':<36}{'b':<36}{'n':>5}{'A':>7}{'B':>7}{'B-A':>8}  "
          f"{'95% CI (cluster boot.)':<22}{'McNemar p':>10}")
    for r in rows:
        print(f"{r['dataset']:<8}{r['metric']:<8}{r['a']:<36}{r['b']:<36}{r['n_pairs']:>5}{100 * r['rate_a']:>6.1f}%"
              f"{100 * r['rate_b']:>6.1f}%{100 * r['diff']:>+7.1f}  [{100 * r['ci_low']:+6.1f}, {100 * r['ci_high']:+6.1f}]"
              f"{r['mcnemar_p']:>13.2g}")
    print(f"\n-> {out / 'pooled_analysis.csv'}")


if __name__ == "__main__":
    main()
