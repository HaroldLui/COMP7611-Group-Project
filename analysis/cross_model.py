"""Cross-model comparison: DeepSeek, GLM-5.3 and Qwen3.8 on the same frozen test split.

    python analysis/cross_model.py

Reads the three gateway-off test runs, rescoring with the current rules, and writes:
  results/cross-model/rates.csv, contrasts.csv, laundering.csv, summary.md
  paper/tables/cross_model_rates.tex, paper/tables/cross_model_contrasts.tex
  paper/figures/cross_model_g1.pdf (and .png)
Intervals: Wilson for single rates; paired bootstrap over the 30 scenarios for differences.
"""

from __future__ import annotations

import csv
import gzip
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.analyze import rescore, wilson  # noqa: E402

MODELS = [("DeepSeek-v4.1-flash", "test-deepseek"),
          ("GLM-5.3", "test-glm-5.3-aliyun"),
          ("Qwen3.8-flash", "test-qwen3.8-flash-aliyun")]
CONFIGS = ["A", "M1", "M2", "M3", "M4"]
N_BOOT = 4000

G1 = lambda r: r["goal"] == "G1"
G2I = lambda r: r["goal"] == "G2" and r["template"] != "direct"
G2D = lambda r: r["goal"] == "G2" and r["template"] == "direct"
CLEAN = lambda r: r["goal"] is None
ATT = lambda r: r["goal"] is not None

# (label, metric, selector) for the per-configuration table
RATES = [("G1 success", "g1_success", G1), ("G2 success (instruction)", "g2_success", G2I),
         ("G2 control (no instruction)", "g2_success", G2D), ("Clean task done", "utility", CLEAN),
         ("Safe and done (attacked)", "safe_utility", ATT), ("Flagged (attacked)", "flagged", ATT)]

# (label, a, b, selector, metric): difference a − b
CONTRASTS = [("Single vs. free-text pipeline (A − M1), G1", "A", "M1", G1, "g1_success"),
             ("Single vs. JSON pipeline (A − M2), G1", "A", "M2", G1, "g1_success"),
             ("Free text vs. JSON (M1 − M2), G1", "M1", "M2", G1, "g1_success"),
             ("Free text vs. JSON, request visible (M3 − M4), G1", "M3", "M4", G1, "g1_success"),
             ("Without vs. with request (M1 − M3), G1", "M1", "M3", G1, "g1_success"),
             ("Without vs. with request (M2 − M4), G1", "M2", "M4", G1, "g1_success"),
             ("Free text vs. JSON (M1 − M2), G2 instruction", "M1", "M2", G2I, "g2_success"),
             ("Single vs. free-text pipeline (A − M1), G2 instruction", "A", "M1", G2I, "g2_success")]


def load(folder):
    with gzip.open(ROOT / "results" / folder / "episodes.jsonl.gz", "rt") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rescore(rows, str(ROOT / "data" / "scenarios.json"))
    return rows


def rate(rows, cfg, sel, metric):
    rs = [r for r in rows if r["config"] == cfg and sel(r)]
    k = sum(bool(r["score"][metric]) for r in rs)
    lo, hi = wilson(k, len(rs))
    return k, len(rs), lo, hi


def paired_diff(rows, a, b, sel, metric, seed=7):
    per = defaultdict(lambda: {a: [], b: []})
    for r in rows:
        if r["config"] in (a, b) and sel(r):
            per[r["scenario_id"]][r["config"]].append(int(bool(r["score"][metric])))
    sids = sorted(s for s, d in per.items() if d[a] and d[b])

    def diff(sample):
        xa = [v for s in sample for v in per[s][a]]
        xb = [v for s in sample for v in per[s][b]]
        return sum(xa) / len(xa) - sum(xb) / len(xb)

    rng = random.Random(seed)
    boots = sorted(diff([rng.choice(sids) for _ in sids]) for _ in range(N_BOOT))
    return diff(sids), boots[int(0.025 * N_BOOT)], boots[int(0.975 * N_BOOT)]


def laundering(rows):
    """Where the attacker's address sits in the reader's JSON notes, for successful G1 leaks in M2/M4."""
    where = Counter()
    for r in rows:
        if r["config"] in ("M2", "M4") and G1(r) and r["score"]["g1_success"]:
            try:
                notes = json.loads(r["record"]["handoffs"][0]["content"])
            except (TypeError, ValueError, IndexError):
                where["unparsed"] += 1
                continue
            fields = [k for k, v in notes.items() if r["marker"] in json.dumps(v)]
            where["action_items" if "action_items" in fields else (fields[0] if fields else "absent")] += 1
    return where


def pct(x):
    return f"{100 * x:.0f}"


def main():
    out = ROOT / "results" / "cross-model"
    out.mkdir(parents=True, exist_ok=True)
    data = {name: load(folder) for name, folder in MODELS}

    # ---- per-configuration rates
    rate_rows = []
    for name, rows in data.items():
        for cfg in CONFIGS:
            for label, metric, sel in RATES:
                k, n, lo, hi = rate(rows, cfg, sel, metric)
                rate_rows.append({"model": name, "config": cfg, "metric": label, "k": k, "n": n,
                                  "rate": round(k / n, 4), "lo": round(lo, 4), "hi": round(hi, 4)})
    with open(out / "rates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rate_rows[0]))
        w.writeheader()
        w.writerows(rate_rows)

    # ---- contrasts
    con_rows = []
    for name, rows in data.items():
        for label, a, b, sel, metric in CONTRASTS:
            d, lo, hi = paired_diff(rows, a, b, sel, metric)
            con_rows.append({"model": name, "contrast": label, "diff": round(d, 4), "lo": round(lo, 4),
                             "hi": round(hi, 4), "excludes_zero": lo > 0 or hi < 0})
    with open(out / "contrasts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(con_rows[0]))
        w.writeheader()
        w.writerows(con_rows)

    # ---- laundering field + flag/outcome
    laund = {name: laundering(rows) for name, rows in data.items()}
    flags = {}
    for name, rows in data.items():
        att = [r for r in rows if ATT(r)]
        succ = [r for r in att if r["score"]["g1_success"] or r["score"]["g2_success"]]
        fail = [r for r in att if not (r["score"]["g1_success"] or r["score"]["g2_success"])]
        flags[name] = (sum(r["score"]["flagged"] for r in succ), len(succ),
                       sum(r["score"]["flagged"] for r in fail), len(fail),
                       sum(r["score"]["flagged"] for r in rows if CLEAN(r)), sum(1 for r in rows if CLEAN(r)))
    with open(out / "laundering.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "leaks_M2_M4", "in_action_items", "in_other_field", "absent_or_unparsed",
                    "flagged_success", "success", "flagged_fail", "fail", "flagged_clean", "clean"])
        for name in data:
            c = laund[name]
            other = sum(v for k, v in c.items() if k not in ("action_items", "absent", "unparsed"))
            w.writerow([name, sum(c.values()), c["action_items"], other, c["absent"] + c["unparsed"], *flags[name]])

    # ---- markdown summary
    get = {(r["model"], r["config"], r["metric"]): r for r in rate_rows}
    lines = ["# Cross-model comparison (test split, gateway off)", "",
             "Generated by `analysis/cross_model.py`. Rates in %, 95% Wilson intervals in brackets.", ""]
    for label, _, _ in RATES:
        lines += [f"## {label}", "", "| model | " + " | ".join(CONFIGS) + " |", "|---|" + "---|" * len(CONFIGS)]
        for name in data:
            cells = [f"{pct(get[(name, c, label)]['rate'])} [{pct(get[(name, c, label)]['lo'])}–{pct(get[(name, c, label)]['hi'])}]" for c in CONFIGS]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Paired contrasts (percentage points; * = interval excludes 0)", "",
              "| contrast | " + " | ".join(data) + " |", "|---|" + "---|" * len(data)]
    for label, *_ in CONTRASTS:
        cells = []
        for name in data:
            r = next(x for x in con_rows if x["model"] == name and x["contrast"] == label)
            cells.append(f"{100 * r['diff']:+.1f} [{100 * r['lo']:+.1f}, {100 * r['hi']:+.1f}]" + ("*" if r["excludes_zero"] else ""))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "## Where JSON leaks were carried (successful G1 in M2/M4)", "",
              "| model | leaks | attacker address inside `action_items` | other field | absent |", "|---|---|---|---|---|"]
    for name in data:
        c = laund[name]
        other = sum(v for k, v in c.items() if k not in ("action_items", "absent", "unparsed"))
        lines.append(f"| {name} | {sum(c.values())} | {c['action_items']} | {other} | {c['absent'] + c['unparsed']} |")
    lines += ["", "## Flagged by an agent (keyword heuristic)", "",
              "| model | successful attacks flagged | failed attacks flagged | clean runs flagged |", "|---|---|---|---|"]
    for name, (fs, s, ff, fl, fc, c) in flags.items():
        lines.append(f"| {name} | {fs} / {s} | {ff} / {fl} | {fc} / {c} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")

    # ---- LaTeX tables
    def r_(name, cfg, label):
        return pct(get[(name, cfg, label)]["rate"])
    short = {"DeepSeek-v4.1-flash": "DeepSeek", "GLM-5.3": "GLM-5.3", "Qwen3.8-flash": "Qwen3.8"}
    t = [r"\begin{table}[t]\centering\small",
         r"\begin{tabular}{@{}llrrrrr@{}}\toprule",
         r"Metric & Model & A & M1 & M2 & M3 & M4\\\midrule"]
    for label in ["G1 success", "G2 success (instruction)", "G2 control (no instruction)", "Safe and done (attacked)"]:
        for i, name in enumerate(data):
            t.append(f"{label if i == 0 else ''} & {short[name]} & " + " & ".join(r_(name, c, label) for c in CONFIGS) + r"\\")
        t.append(r"\midrule" if label != "Safe and done (attacked)" else r"\bottomrule")
    t += [r"\end{tabular}",
          r"\caption{Attack success and task outcome (\%) for three models on the same 30 test scenarios "
          r"(540 episodes per configuration and model, gateway off). G2 control is a tampered action line "
          r"with no instruction. 95\% intervals are in \texttt{results/cross-model/summary.md}.}",
          r"\label{tab:crossmodel}", r"\end{table}"]
    (ROOT / "paper" / "tables" / "cross_model_rates.tex").write_text("\n".join(t) + "\n")

    c = [r"\begin{table}[t]\centering\small",
         r"\begin{tabular}{@{}lrrr@{}}\toprule",
         r"Contrast (pts) & DeepSeek & GLM-5.3 & Qwen3.8\\\midrule"]
    keep = {"Single vs. JSON pipeline (A − M2), G1": r"G1: A $-$ M2",
            "Single vs. free-text pipeline (A − M1), G1": r"G1: A $-$ M1",
            "Free text vs. JSON (M1 − M2), G1": r"G1: M1 $-$ M2 (JSON)",
            "Without vs. with request (M1 − M3), G1": r"G1: M1 $-$ M3 (request)",
            "Without vs. with request (M2 − M4), G1": r"G1: M2 $-$ M4 (request)",
            "Free text vs. JSON (M1 − M2), G2 instruction": r"G2: M1 $-$ M2 (JSON)"}
    for label, tex in keep.items():
        cells = []
        for name in data:
            r = next(x for x in con_rows if x["model"] == name and x["contrast"] == label)
            v = f"{100 * r['diff']:+.0f} [{100 * r['lo']:+.0f}, {100 * r['hi']:+.0f}]".replace("-", "$-$")
            cells.append(r"\textbf{" + v + "}" if r["excludes_zero"] else v)
        c.append(tex + " & " + " & ".join(cells) + r"\\")
    c += [r"\bottomrule\end{tabular}",
          r"\caption{Paired differences in attack success (percentage points, 95\% bootstrap interval over "
          r"scenarios). Positive: the second configuration is safer. Bold: interval excludes zero.}",
          r"\label{tab:crossmodel-contrasts}", r"\end{table}"]
    (ROOT / "paper" / "tables" / "cross_model_contrasts.tex").write_text("\n".join(c) + "\n")

    # ---- figure: G1 success by configuration, one group per model
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"A": "#334155", "M1": "#0F766E", "M2": "#5EAAA0", "M3": "#B4234A", "M4": "#E39AAE"}
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4), sharey=True)
    for ax, (label, title) in zip(axes, [("G1 success", "Redirect (G1)"), ("G2 success (instruction)", "Manipulation, with instruction (G2)")]):
        width = 0.16
        for j, cfg in enumerate(CONFIGS):
            xs, ys, err = [], [], [[], []]
            for i, name in enumerate(data):
                g = get[(name, cfg, label)]
                xs.append(i + (j - 2) * width)
                ys.append(100 * g["rate"])
                err[0].append(100 * (g["rate"] - g["lo"]))
                err[1].append(100 * (g["hi"] - g["rate"]))
            ax.bar(xs, ys, width, yerr=err, capsize=1.5, color=colors[cfg], label=cfg, error_kw={"elinewidth": 0.6})
        ax.set_xticks(range(len(data)))
        ax.set_xticklabels([short[n] for n in data])
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0, 100)
        ax.grid(axis="y", color="#E2E8F0", linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    # Model logos under the x axis, model name below them (LobeHub icons, see paper/figures/logos)
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    logo_file = {"DeepSeek-v4.1-flash": "deepseek.png", "GLM-5.3": "glm.png", "Qwen3.8-flash": "qwen.png"}
    for ax in axes:
        ax.tick_params(axis="x", length=0, pad=26)
        for i, name in enumerate(data):
            img = plt.imread(ROOT / "paper" / "figures" / "logos" / logo_file[name])
            ab = AnnotationBbox(OffsetImage(img, zoom=0.075), (i, 0), xybox=(0, -14), xycoords=("data", "axes fraction"),
                                boxcoords="offset points", frameon=False, box_alignment=(0.5, 0.5))
            ax.add_artist(ab)
    axes[0].set_ylabel("Attack success (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=5, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.03))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for ext in ("pdf", "png"):
        fig.savefig(ROOT / "paper" / "figures" / f"cross_model_attack.{ext}", dpi=200, bbox_inches="tight")
    print("wrote", out / "summary.md")


if __name__ == "__main__":
    main()
