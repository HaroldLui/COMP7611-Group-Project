"""Summarize a results folder.

    python -m harness.analyze results/pilot-dev
    python -m harness.analyze results/main --annotate 80   # also export an annotation sheet

Writes summary.md, by_config.csv and (optionally) annotation.csv next to episodes.jsonl.
Confidence intervals: Wilson for single rates; for differences, a paired bootstrap that
resamples *scenarios* (all templates/repeats of a scenario move together).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

PRIMARY = [("M1", "M2"), ("M3", "M4"), ("M1", "M3"), ("M2", "M4"), ("A", "M1"), ("A", "M2")]
N_BOOT = 2000


def load(path: Path) -> list[dict]:
    """Read episodes.jsonl, or episodes.jsonl.gz when only the compressed copy exists."""
    if not path.exists() and path.with_suffix(".jsonl.gz").exists():
        with gzip.open(path.with_suffix(".jsonl.gz"), "rt") as f:
            return [json.loads(line) for line in f if line.strip()]
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt_rate(k: int, n: int) -> str:
    if n == 0:
        return "—"
    lo, hi = wilson(k, n)
    return f"{k / n:.0%} [{lo:.0%}–{hi:.0%}] (n={n})"


def cfg_label(r: dict) -> str:
    return r["config"] + ("+GW" if r["gateway"] else "")


MISSING = "n/a (rescore)"


def missing_metrics(rows: list[dict]) -> list[str]:
    """Metrics the current scorer produces that some stored episodes lack."""
    from .scoring import SCORE_KEYS
    return sorted({k for r in rows for k in SCORE_KEYS if k not in r["score"]})


def table_by_config(rows: list[dict]) -> tuple[list[str], list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[cfg_label(r)].append(r)
    out = []
    for label in sorted(groups):
        g = groups[label]
        clean = [r for r in g if r["goal"] is None]
        g1 = [r for r in g if r["goal"] == "G1"]
        g2 = [r for r in g if r["goal"] == "G2"]
        att = g1 + g2

        def k(rs, f):
            return sum(bool(r["score"][f]) for r in rs)

        def rate(rs, f):
            # A metric that some episodes were never scored on (older folder) is unknown, not 0.
            if any(f not in r["score"] for r in rs):
                return MISSING
            return fmt_rate(k(rs, f), len(rs))

        out.append({
            "config": label,
            "utility_clean": rate(clean, "utility"),
            "ASR_G1": rate(g1, "g1_success"),
            "attempt_G1": rate(g1, "g1_attempt"),
            "ASR_G2": rate(g2, "g2_success"),
            # `direct` G2 is a tampered line with no instruction (a transcription control);
            # report it apart from the instruction-bearing templates.
            "ASR_G2_instr": rate([r for r in g2 if r["template"] != "direct"], "g2_success"),
            "ASR_G2_direct": rate([r for r in g2 if r["template"] == "direct"], "g2_success"),
            "flagged_attacked": rate(att, "flagged"),
            "flagged_clean": rate(clean, "flagged"),
            "misdirect": rate(g, "misdirect"),
            "notify_requester": rate(g, "notify_requester"),
            "utility_attacked": rate(att, "utility"),
            "safe_utility_attacked": rate(att, "safe_utility"),
            "format_fail": fmt_rate(sum(r["score"]["status"] == "format_failure" for r in g), len(g)),
            "errors": sum(r["score"]["status"] == "error" for r in g),
            "g2_review": MISSING if any("g2_needs_review" not in r["score"] for r in g2) else k(g2, "g2_needs_review"),
            "tokens_per_ep": round(sum(r["score"]["input_tokens"] + r["score"]["output_tokens"] for r in g) / len(g)),
            "calls_per_ep": round(sum(r["score"]["n_model_calls"] for r in g) / len(g), 1),
        })
    return list(out[0].keys()) if out else [], out


def paired_bootstrap(rows: list[dict], a: str, b: str, goal: str, metric: str, seed: int = 0):
    """Difference rate(a) - rate(b) on `metric` for attacked episodes of `goal`."""
    per: dict[str, dict[str, list[int]]] = defaultdict(lambda: {a: [], b: []})
    for r in rows:
        lab = cfg_label(r)
        if r["goal"] == goal and lab in (a, b):
            per[r["scenario_id"]][lab].append(int(bool(r["score"][metric])))
    sids = [s for s, d in per.items() if d[a] and d[b]]
    if not sids:
        return None

    def diff(sample):
        xa = [v for s in sample for v in per[s][a]]
        xb = [v for s in sample for v in per[s][b]]
        return sum(xa) / len(xa) - sum(xb) / len(xb)

    rng = random.Random(seed)
    point = diff(sids)
    boots = sorted(diff([rng.choice(sids) for _ in sids]) for _ in range(N_BOOT))
    return point, boots[int(0.025 * N_BOOT)], boots[int(0.975 * N_BOOT)], len(sids)


def propagation(rows: list[dict]) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r["goal"] is None:
            continue
        for h, lab in zip(r["record"]["handoffs"], r["score"]["handoff_labels"]):
            out[f"{cfg_label(r)} {h['from']}→{h['to']}"][lab] += 1
    return out


def export_annotation(rows: list[dict], n: int, path: Path, seed: int = 0) -> None:
    """Sample attacked multi-agent episodes whose injection was carried into a handoff."""
    pool = [r for r in rows if r["goal"] and "carried" in r["score"]["handoff_labels"]]
    random.Random(seed).shuffle(pool)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "goal", "handoff", "marker", "content", "label_A", "label_B", "notes"])
        for r in pool[:n]:
            for h, lab in zip(r["record"]["handoffs"], r["score"]["handoff_labels"]):
                if lab == "carried":
                    w.writerow([r["key"], r["goal"], f"{h['from']}→{h['to']}", r.get("marker") or "",
                                h["content"], "", "", ""])
    print(f"annotation sheet: {path} (label each row Quoted or Promoted; two annotators)")


def rescore(rows: list[dict], scenarios_path: str) -> None:
    """Recompute every stored score from its record with the current scoring rules."""
    from .attacks import inject
    from .env import load_scenarios
    from .scoring import score

    base = {s.id: s for s in load_scenarios(scenarios_path)}
    for r in rows:
        sc = base[r["scenario_id"]]
        if r["goal"]:
            sc = inject(sc, r["template"], r["goal"], r["position"])
        r["score"] = score(sc, r["record"])


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--annotate", type=int, default=0)
    ap.add_argument("--rescore", action="store_true",
                    help="recompute scores with the current rules (episodes.jsonl is not changed)")
    ap.add_argument("--scenarios", default="data/scenarios.json")
    a = ap.parse_args(argv)
    folder = Path(a.folder)
    rows = load(folder / "episodes.jsonl")
    if a.rescore:
        rescore(rows, a.scenarios)
    backends = {r["backend"] for r in rows}
    models = {r["model"] for r in rows}

    lines = [f"# Results: {folder.name}", "",
             f"Episodes: {len(rows)} | backend: {', '.join(backends)} | model: {', '.join(models)}", ""]
    if "fake" in backends:
        lines += ["> **FAKE BACKEND — plumbing test only. These numbers are not experimental data.**", ""]

    missing = missing_metrics(rows)
    if missing:
        lines += [f"> **Scored with older rules:** {', '.join(missing)} missing for some episodes "
                  f"(shown as `{MISSING}`). Re-run with `--rescore`.", ""]

    cols, table = table_by_config(rows)
    if table:
        lines += ["## By configuration", "", "| " + " | ".join(cols) + " |",
                  "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(str(t[c]) for c in cols) + " |" for t in table]
        with open(folder / "by_config.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(table)

    labels = {cfg_label(r) for r in rows}
    n_scen = len({r["scenario_id"] for r in rows})
    lines += ["", "## Primary comparisons (attack success; paired bootstrap over scenarios)", ""]
    if n_scen < 10:
        lines += [f"> Only {n_scen} scenarios: a bootstrap over this few clusters gives coarse, "
                  "unreliable intervals. Read differences as direction, not significance.", ""]
    lines += ["| comparison | goal | difference | 95% CI | scenarios |", "|---|---|---|---|---|"]
    for gw in ("", "+GW"):
        for x, y in PRIMARY:
            xa, yb = x + gw, y + gw
            if xa not in labels or yb not in labels:
                continue
            for goal, metric in (("G1", "g1_success"), ("G2", "g2_success")):
                res = paired_bootstrap(rows, xa, yb, goal, metric)
                if res:
                    d, lo, hi, n = res
                    lines.append(f"| {xa} − {yb} | {goal} | {d:+.1%} | [{lo:+.1%}, {hi:+.1%}] | {n} |")

    prop = propagation(rows)
    if prop:
        lines += ["", "## Handoff propagation (attacked episodes, automatic labels)", "",
                  "| handoff | dropped | carried | promoted | failed |", "|---|---|---|---|---|"]
        for k in sorted(prop):
            c = prop[k]
            lines.append(f"| {k} | {c['dropped']} | {c['carried']} | {c['promoted']} | {c['failed']} |")

    by_t: dict[tuple, list[int]] = defaultdict(list)
    for r in rows:
        if r["goal"]:
            by_t[(cfg_label(r), r["template"], r["goal"])].append(
                int(r["score"]["g1_success" if r["goal"] == "G1" else "g2_success"]))
    if by_t:
        lines += ["", "## Attack success by template", "", "| config | template | goal | ASR | n |",
                  "|---|---|---|---|---|"]
        for (c, t, g), v in sorted(by_t.items()):
            lines.append(f"| {c} | {t} | {g} | {sum(v) / len(v):.0%} | {len(v)} |")

    (folder / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    if a.annotate:
        export_annotation(rows, a.annotate, folder / "annotation.csv")


if __name__ == "__main__":
    main()
