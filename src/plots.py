"""
plots.py — result figures for the paper.

  python src/plots.py                      # from results/test_final/ (TEST data)
  python src/plots.py --dir results/dev_run2_final --split dev

Output in <dir>/figures/:
  fig1_asr_per_attack.png/.pdf   ASR per attack type, per model: no defense vs content-only gate vs Trust Gate
  fig2_tradeoff.png/.pdf         ASR (A1–A3 pooled) vs dialog FRR trade-off, every condition, per model
  figure_data.csv                the exact numbers plotted (companion table)

Colors: first 3 slots of a validated categorical palette (blue, orange, aqua; colorblind-safe for every pair).
Ablations are drawn in gray + text labels (not a 4th/5th color). Confidence intervals = 95% Wilson.
"""
import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import wilson  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = [("ollama_qwen3_8b", "qwen3:8b"), ("ollama_gemma4_12b", "gemma4:12b"),
          ("ollama_llama3.1_8b", "llama3.1:8b"), ("ollama_olmo-3_7b-instruct", "olmo-3:7b")]
ATTACKS = [("A1_false_fact", "A1\nfalse fact"), ("A2_confident_poison", "A2\nconfident"),
           ("A3_external_source", "A3\nexternal"), ("A3_auth", "A3-auth\nsend_file")]
MAIN = [("no_defense", "No defense", "#2a78d6"), ("content_only", "Content-only gate", "#eb6834"),
        ("trust", "Trust Gate", "#1baf7a")]
ABLATIONS = [("ablate_source", "without source trust"), ("ablate_poison_risk", "without poisoning risk")]
CODE = {"No defense": "N", "Content-only gate": "C", "Trust Gate": "T", "without source trust": "−S",
        "without poisoning risk": "−R"}  # short in-plot labels; meanings are given in the caption
INK, INK2, MUTED, GRID, SURFACE, ABL = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb", "#8a8984"

plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.titlecolor": INK, "figure.facecolor": SURFACE,
                     "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE})


def load(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


def summary_lookup(rows):
    return {(r["condition"], r["metric"]): r for r in rows}


def pooled_asr(exp_rows, cond):
    rs = [r for r in exp_rows if r["condition"] == cond and r["kind"] in [a for a, _ in ATTACKS[:3]]]
    k = sum(r["outcome"] == "success" for r in rs)
    return (k, len(rs)) + wilson(k, len(rs))


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig1(data_dir, split, out, table):
    fig, axes = plt.subplots(1, len(MODELS), figsize=(12, 3.4), sharey=True)
    width = 0.26
    for ax, (tag, label) in zip(axes, MODELS):
        s = summary_lookup(load(data_dir / f"summary_{split}_{tag}.csv"))
        for j, (cond, name, color) in enumerate(MAIN):
            xs, ys, lo, hi = [], [], [], []
            for i, (att, _) in enumerate(ATTACKS):
                r = s[(cond, f"ASR_{att}")]
                p, l, h = (float(r[k]) * 100 if r[k] != "" else float("nan") for k in ("rate", "ci_low", "ci_high"))
                xs.append(i + (j - 1) * width); ys.append(p); lo.append(p - l); hi.append(h - p)
                table.append({"figure": "fig1", "model": label, "condition": name, "attack": att, "asr_pct": round(p, 1),
                              "ci_low": round(l, 1), "ci_high": round(h, 1), "k": r["k"], "n": r["n"]})
            ax.bar(xs, ys, width=width, color=color, edgecolor=SURFACE, linewidth=1.5, label=name, zorder=2)
            ax.errorbar(xs, ys, yerr=[lo, hi], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=2, zorder=3)
            if cond == "trust":  # value labels for the Trust Gate only (selective), above the CI so they do not collide
                for x, y, h in zip(xs, ys, hi):
                    ax.text(x, y + h + 1.5, f"{y:.0f}", ha="center", va="bottom", fontsize=7, color=INK)
        ax.set_xticks(range(len(ATTACKS)), [a for _, a in ATTACKS], fontsize=8)
        ax.set_title(label, fontsize=10, loc="left")
        ax.set_ylim(0, 105)
        style(ax)
    axes[0].set_ylabel("ASR (%) — successful attacks")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.text(0.5, -0.06, f"{split.capitalize()} split. Whiskers = 95% confidence interval (Wilson). A1–A3: n = {'34' if split == 'test' else '15'} "
             f"per attack; A3-auth: n = {'7' if split == 'test' else '3'}. Numbers above bars = Trust Gate.",
             ha="center", fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig1_asr_per_attack.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig2(data_dir, split, out, table):
    fig, axes = plt.subplots(1, len(MODELS), figsize=(12, 3.4), sharey=True, sharex=True)
    for ax, (tag, label) in zip(axes, MODELS):
        s = summary_lookup(load(data_dir / f"summary_{split}_{tag}.csv"))
        exp = load(data_dir / f"exp_{split}_{tag}.csv")
        # Ablations are drawn first (underneath) so main points stay visible; identical positions -> labels merged.
        conds = [(c, n, ABL, False) for c, n in ABLATIONS] + [(c, n, col, True) for c, n, col in MAIN]
        points = {}
        for cond, name, color, main in conds:
            k, n, p, lo, hi = pooled_asr(exp, cond)
            if cond == "no_defense":
                fx, flo, fhi, fk, fn = 0.0, 0.0, 0.0, 0, 0
            else:
                r = s[(cond, "FRR_dialog")]
                fx, flo, fhi = (float(r[x]) * 100 for x in ("rate", "ci_low", "ci_high"))
                fk, fn = r["k"], r["n"]
            y, ylo, yhi = p * 100, lo * 100, hi * 100
            ax.errorbar(fx, y, xerr=[[fx - flo], [fhi - fx]], yerr=[[y - ylo], [yhi - y]], fmt="none", ecolor=color,
                        elinewidth=0.8, alpha=0.7, zorder=2)
            ax.scatter(fx, y, s=55 if main else 35, color=color, edgecolor=SURFACE, linewidth=1.5, zorder=3,
                       marker="o" if main else "D", label=name if main else None)
            points.setdefault((round(fx, 1), round(y, 1)), []).append(name)
            table.append({"figure": "fig2", "model": label, "condition": name, "asr_pooled_pct": round(y, 1),
                          "asr_ci": f"{ylo:.1f}-{yhi:.1f}", "k": k, "n": n, "frr_dialog_pct": round(fx, 1),
                          "frr_ci": f"{flo:.1f}-{fhi:.1f}", "frr_k": fk, "frr_n": fn})
        order = [n for _, n, _ in MAIN] + [n for _, n in ABLATIONS]
        for (fx, y), names in points.items():
            only_ablation = all(n not in [m for _, m, _ in MAIN] for n in names)
            ax.annotate(" = ".join(CODE[n] for n in sorted(names, key=order.index)), (fx, y),
                        xytext=(6, -9 if only_ablation else 3), textcoords="offset points", fontsize=7.5, color=INK)
        ax.set_title(label, fontsize=10, loc="left")
        ax.set_xlabel("Dialog FRR (%) — clean memories held back")
        ax.set_xlim(-3, 75)
        ax.set_ylim(0, 65)
        style(ax)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
    axes[0].set_ylabel("ASR, A1–A3 pooled (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.text(0.5, -0.1, f"{split.capitalize()} split. Lower left = better (few successful attacks, few clean memories lost). "
             "Whiskers = 95% Wilson.\nN = no defense, C = content-only gate, T = Trust Gate, "
             "−S = ablation without source trust, −R = ablation without poisoning risk (gray diamonds). "
             "\"=\" means identical results.", ha="center", fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig2_tradeoff.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results/test_final")
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    args = ap.parse_args()
    data_dir = ROOT / args.dir
    out = data_dir / "figures"
    out.mkdir(exist_ok=True)
    table = []
    fig1(data_dir, args.split, out, table)
    fig2(data_dir, args.split, out, table)
    with open(out / "figure_data.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in table for k in r}))
        w.writeheader()
        w.writerows(table)
    print(f"Figures + table in {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
