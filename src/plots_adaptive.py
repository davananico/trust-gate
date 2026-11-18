"""
plots_adaptive.py — figure for the adaptive attacks (AD1, AD2) next to the original attacks (A1, A2), TEST split.

  python src/plots_adaptive.py

Reads results/test_final/summary_test_<model>.csv (A1, A2) and
results/adaptive/adaptive_summary_test_<model>_AD1-AD2-AD4.csv (AD1, AD2). Output in results/adaptive/figures/:
  fig3_adaptive.png/.pdf   top: PMAR under the Trust Gate; bottom: ASR no defense vs Trust Gate
  fig3_data.csv            the exact numbers plotted

Not plotted: AD4 (n = 7 per model; reported as a table) and AD3 (only qwen3 finished on test).
Colors and style are those of plots.py (blue = no defense, aqua = Trust Gate), so the figures read as one set.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plots import INK, INK2, MAIN, MODELS, ROOT, SURFACE, load, plt, style, summary_lookup  # noqa: E402

ATTACKS = [("A1_false_fact", "A1\nfalse fact"), ("A2_confident_poison", "A2\nconfident"),
           ("AD1_split_assertion", "AD1\nsplit"), ("AD2_lexicon_free", "AD2\nlexicon-free")]
COLOR = {c: col for c, _, col in MAIN}
NAME = {c: n for c, n, _ in MAIN}


def cell(s, cond, metric):
    r = s[(cond, metric)]
    p, lo, hi = (float(r[k]) * 100 for k in ("rate", "ci_low", "ci_high"))
    return p, lo, hi, r["k"], r["n"]


def bars(ax, xs, vals, color, label, labelled, width):
    ys = [v[0] for v in vals]
    ax.bar(xs, ys, width=width, color=color, edgecolor=SURFACE, linewidth=1.5,
           label=label, zorder=2)
    ax.errorbar(xs, ys, yerr=[[v[0] - v[1] for v in vals], [v[2] - v[0] for v in vals]], fmt="none", ecolor=INK2,
                elinewidth=0.8, capsize=2, zorder=3)
    if labelled:  # value labels above the CI, as in fig1
        for x, v in zip(xs, vals):
            ax.text(x, v[2] + 1.5, f"{v[0]:.0f}", ha="center", va="bottom", fontsize=7, color=INK)


def main():
    out = ROOT / "results" / "adaptive" / "figures"
    out.mkdir(exist_ok=True)
    fig, axes = plt.subplots(2, len(MODELS), figsize=(12, 6.2), sharey=True)
    table = []
    for col, (tag, label) in enumerate(MODELS):
        s = summary_lookup(load(ROOT / "results" / "test_final" / f"summary_test_{tag}.csv"))
        s.update(summary_lookup(load(ROOT / "results" / "adaptive" / f"adaptive_summary_test_{tag}_AD1-AD2-AD4.csv")))
        x = range(len(ATTACKS))

        pmar = [cell(s, "trust", f"PMAR_{a}") for a, _ in ATTACKS]
        bars(axes[0, col], list(x), pmar, COLOR["trust"], None, True, 0.5)
        for (a, _), v in zip(ATTACKS, pmar):
            table.append({"panel": "PMAR", "model": label, "condition": NAME["trust"], "attack": a,
                          "pct": round(v[0], 1), "ci_low": round(v[1], 1), "ci_high": round(v[2], 1), "k": v[3], "n": v[4]})

        for j, cond in enumerate(("no_defense", "trust")):
            asr = [cell(s, cond, f"ASR_{a}") for a, _ in ATTACKS]
            bars(axes[1, col], [i + (j - 0.5) * 0.36 for i in x], asr, COLOR[cond], NAME[cond], cond == "trust", 0.36)
            for (a, _), v in zip(ATTACKS, asr):
                table.append({"panel": "ASR", "model": label, "condition": NAME[cond], "attack": a,
                              "pct": round(v[0], 1), "ci_low": round(v[1], 1), "ci_high": round(v[2], 1), "k": v[3], "n": v[4]})

        axes[0, col].set_title(label, fontsize=10, loc="left")
        for ax in axes[:, col]:
            ax.set_xticks(list(x), [a for _, a in ATTACKS], fontsize=8)
            ax.set_ylim(0, 105)
            style(ax)
    axes[0, 0].set_ylabel("PMAR (%) — poison accepted\nby the Trust Gate")
    axes[1, 0].set_ylabel("ASR (%) — successful attacks")
    handles, labels = axes[1, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.01))
    fig.text(0.5, -0.04, "Test split. A1/A2 = original attacks (main run); "
             "AD1/AD2 = adaptive attacks against the same locked gate (AD1: assertion moved to its own line; AD2: assertion reworded without lexicon words).\n"
             "Whiskers = 95% Wilson. ASR: n = 34 per attack and model; PMAR: n = poison memories written (23–39). "
             "Numbers above bars = Trust Gate.", ha="center", fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig3_adaptive.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    with open(out / "fig3_data.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    print(f"Figure + table in {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
