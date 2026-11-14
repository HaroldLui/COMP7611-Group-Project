"""Post hoc analyses quoted in paper/report.tex (not preregistered; labelled as such in the text).

    python analysis/report_extras.py > results/cross-model/report_extras.md
"""
import gzip, json, random
from collections import defaultdict, Counter

RUNS = {"DeepSeek": "results/test-deepseek", "GLM-5.3": "results/test-glm-5.3-aliyun",
        "Qwen3.8": "results/test-qwen3.8-flash-aliyun"}
MS = ["M1", "M2", "M3", "M4"]
CFG = ["A"] + MS
NB = 2000


def load(d):
    return [json.loads(l) for l in gzip.open(d + "/episodes.jsonl.gz", "rt") if l.strip()]


def boot(per, f, seed=0):
    sids = sorted(per)
    rng = random.Random(seed)
    pt = f(sids)
    bs = sorted(f([rng.choice(sids) for _ in sids]) for _ in range(NB))
    return pt, bs[int(.025 * NB)], bs[int(.975 * NB)]


def rate(per, sample, c):
    x = [v for s in sample for v in per[s][c]]
    return sum(x) / len(x)


for name, d in RUNS.items():
    rows = load(d)
    print(f"\n# {name}\n")
    g1 = [r for r in rows if r["goal"] == "G1"]
    per = defaultdict(lambda: defaultdict(list))
    for r in g1:
        per[r["scenario_id"]][r["config"]].append(int(r["score"]["g1_success"]))
    R = lambda s, c: rate(per, s, c)
    eff = {
        "JSON main effect ((M1-M2)+(M3-M4))/2": lambda s: ((R(s, "M1") - R(s, "M2")) + (R(s, "M3") - R(s, "M4"))) / 2,
        "Request main effect ((M1-M3)+(M2-M4))/2": lambda s: ((R(s, "M1") - R(s, "M3")) + (R(s, "M2") - R(s, "M4"))) / 2,
        "Interaction (M2-M4)-(M1-M3)": lambda s: (R(s, "M2") - R(s, "M4")) - (R(s, "M1") - R(s, "M3")),
        "A - mean(M1..M4)": lambda s: R(s, "A") - sum(R(s, m) for m in MS) / 4,
    }
    print("## Factorial effects, G1 (points)")
    for k, f in eff.items():
        p, lo, hi = boot(per, f)
        print(f"- {k}: {100*p:+.1f} [{100*lo:+.1f}, {100*hi:+.1f}]")

    print("## Scenario heterogeneity, G1")
    for c in CFG:
        v = sorted(sum(per[s][c]) / len(per[s][c]) for s in per)
        print(f"- {c}: min {v[0]:.2f} median {v[len(v)//2]:.2f} max {v[-1]:.2f}; scenarios with 0 successes: {sum(x==0 for x in v)}")
    for m in ["M1", "M2"]:
        gt = sum(sum(per[s]["A"]) > sum(per[s][m]) for s in per)
        lt = sum(sum(per[s]["A"]) < sum(per[s][m]) for s in per)
        print(f"- scenarios A>{m}: {gt}, A<{m}: {lt}, tie: {30-gt-lt}")

    print("## Repeat agreement (same scenario/template/goal/config, 2 repeats)")
    cell = defaultdict(list)
    for r in rows:
        if r["goal"]:
            cell[(r["scenario_id"], r["template"], r["goal"], r["config"])].append(
                int(r["score"]["g1_success" if r["goal"] == "G1" else "g2_success"]))
    for g in ("G1", "G2"):
        v = [x for k, x in cell.items() if k[2] == g and len(x) == 2]
        print(f"- {g}: {sum(a==b for a,b in v)}/{len(v)} cells agree ({sum(a==b for a,b in v)/len(v):.0%})")

    print("## Success conditional on flag (attacked episodes)")
    for c in CFG:
        a = [r for r in rows if r["goal"] and r["config"] == c]
        succ = lambda r: r["score"]["g1_success"] or r["score"]["g2_success"]
        f = [r for r in a if r["score"]["flagged"]]
        nf = [r for r in a if not r["score"]["flagged"]]
        print(f"- {c}: flagged {len(f)}/{len(a)}; success|flagged {sum(map(succ,f))}/{len(f)}; success|unflagged {sum(map(succ,nf))}/{len(nf)}")

    print("## G1 funnel in pipelines (labels: reader->planner, planner->executor)")
    for c in MS:
        a = [r for r in g1 if r["config"] == c and len(r["score"]["handoff_labels"]) == 2]
        h1 = [r for r in a if r["score"]["handoff_labels"][0] != "dropped"]
        h2 = [r for r in h1 if r["score"]["handoff_labels"][1] != "dropped"]
        h2all = [r for r in a if r["score"]["handoff_labels"][1] != "dropped"]
        s = [r for r in h2 if r["score"]["g1_success"]]
        sall = sum(r["score"]["g1_success"] for r in a)
        print(f"- {c}: n={len(a)} survive h1 {len(h1)} -> survive h2 {len(h2)} (h2 any {len(h2all)}) -> sent {len(s)} (all successes {sall})")

    print("## G1 by template")
    t = defaultdict(list)
    for r in g1:
        t[(r["template"], r["config"])].append(int(r["score"]["g1_success"]))
    for tp in ["direct", "authority", "fixit", "role"]:
        print(f"- {tp}: " + " ".join(f"{c} {100*sum(t[(tp,c)])/len(t[(tp,c)]):.0f}" for c in CFG))
    print("## G2 by template")
    t = defaultdict(list)
    for r in rows:
        if r["goal"] == "G2":
            t[(r["template"], r["config"])].append(int(r["score"]["g2_success"]))
    for tp in ["direct", "authority", "fixit", "role"]:
        print(f"- {tp}: " + " ".join(f"{c} {100*sum(t[(tp,c)])/len(t[(tp,c)]):.0f}" for c in CFG))

    print("## Cost")
    for c in CFG:
        a = [r for r in rows if r["config"] == c]
        tok = sum(r["score"]["input_tokens"] + r["score"]["output_tokens"] for r in a) / len(a)
        lat = sorted(r["score"]["latency_s"] for r in a)[len(a)//2]
        att = [r for r in a if r["goal"]]
        su = sum(r["score"]["safe_utility"] for r in att)
        print(f"- {c}: tokens/ep {tok:.0f}; median latency {lat:.1f}s; tokens per safe completed attacked episode {sum(r['score']['input_tokens']+r['score']['output_tokens'] for r in att)/max(su,1):.0f}")
