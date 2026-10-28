"""Run a batch of episodes and append them to <out>/episodes.jsonl (resumable).

Model profiles live in configs/models.toml, API keys in .env.

Examples
    # offline plumbing check, no API calls
    python -m harness.run --profile fake --split dev --out results/fake-dev

    # show the plan and its size without running anything
    python -m harness.run --profile deepseek --split test --dry-run

    # pilot on a real model
    python -m harness.run --profile deepseek --split dev --configs A,M1,M2 \\
        --repeats 1 --clean-repeats 1 --out results/pilot-dev --workers 4
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .attacks import GOALS, POSITIONS, TEMPLATES, inject
from .env import load_scenarios
from .config import load_dotenv, load_profile, make_backend, public
from .pipeline import CONFIGS, run_episode
from .scoring import score


def build_plan(args) -> list[dict]:
    scenarios = [s for s in load_scenarios(args.scenarios) if s.split == args.split]
    if args.limit_scenarios:
        scenarios = scenarios[: args.limit_scenarios]
    gateways = {"off": [False], "on": [True], "both": [False, True]}[args.gateway]
    plan = []
    for sc in scenarios:
        variants = [(sc, r) for r in range(args.clean_repeats)]
        for t in args.templates:
            for g in args.goals:
                for p in args.positions:
                    v = inject(sc, t, g, p)
                    variants += [(v, r) for r in range(args.repeats)]
        for v, rep in variants:
            for c in args.configs:
                for gw in gateways:
                    key = f"{v.id}|{v.condition}|{c}|{'GW' if gw else 'noGW'}|r{rep}"
                    plan.append({"key": key, "scenario": v, "config": c, "gateway": gw, "rep": rep})
    return plan


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="fake", help="profile name in configs/models.toml")
    ap.add_argument("--config", default=None, help="alternative profiles file")
    ap.add_argument("--model", default=None, help="override the profile's model")
    ap.add_argument("--scenarios", default="data/scenarios.json")
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--limit-scenarios", type=int, default=0)
    ap.add_argument("--configs", default="A,M1,M2,M3,M4")
    ap.add_argument("--gateway", default="off", choices=["off", "on", "both"])
    ap.add_argument("--templates", default=",".join(TEMPLATES))
    ap.add_argument("--goals", default=",".join(GOALS))
    ap.add_argument("--positions", default="body", help=f"comma list from {POSITIONS}")
    ap.add_argument("--repeats", type=int, default=2, help="repeats per attacked variant")
    ap.add_argument("--clean-repeats", type=int, default=2)
    ap.add_argument("--out", default="results/run")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--max-episodes", type=int, default=0, help="stop after N new episodes (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    for name in ("configs", "templates", "goals", "positions"):
        setattr(args, name, [x for x in getattr(args, name).split(",") if x])
    bad = [c for c in args.configs if c not in CONFIGS]
    if bad:
        ap.error(f"unknown configs {bad}; choose from {list(CONFIGS)}")

    plan = build_plan(args)
    out = Path(args.out)
    path = out / "episodes.jsonl"
    done = set()
    if path.exists():
        with open(path) as f:
            done = {json.loads(line)["key"] for line in f if line.strip()}
    todo = [p for p in plan if p["key"] not in done]
    if args.max_episodes:
        todo = todo[: args.max_episodes]

    n_clean = sum(p["scenario"].injection is None for p in plan)
    print(f"plan: {len(plan)} episodes ({n_clean} clean, {len(plan) - n_clean} attacked) | "
          f"already done: {len(plan) - len([p for p in plan if p['key'] not in done])} | to run now: {len(todo)}")
    print(f"configs={args.configs} gateway={args.gateway} split={args.split}")
    if args.dry_run or not todo:
        return

    load_dotenv()
    profile = load_profile(args.profile, *([Path(args.config)] if args.config else []))
    if args.model:
        profile["model"] = args.model
    backend = make_backend(profile)
    out.mkdir(parents=True, exist_ok=True)
    (out / "run_args.json").write_text(json.dumps(
        vars(args) | {"profile_settings": public(profile), "backend_model": backend.model}, indent=2))
    lock = threading.Lock()

    def work(p):
        rec = run_episode(p["scenario"], CONFIGS[p["config"]], backend, p["gateway"])
        sc = p["scenario"]
        row = {"key": p["key"], "scenario_id": sc.id, "condition": sc.condition,
               "template": sc.injection.template if sc.injection else None,
               "goal": sc.injection.goal if sc.injection else None,
               "position": sc.injection.position if sc.injection else None,
               "marker": sc.injection.marker if sc.injection else None,
               "config": p["config"], "gateway": p["gateway"], "rep": p["rep"],
               "profile": args.profile, "backend": backend.name, "model": backend.model,
               "effort": getattr(backend, "effort", None),
               "score": score(sc, rec), "record": rec}
        with lock, open(path, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
        return row

    n = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, p) for p in todo]
        for fut in as_completed(futs):
            row = fut.result()
            n += 1
            s = row["score"]
            print(f"[{n}/{len(todo)}] {row['key']}  status={s['status']} util={int(s['utility'])} "
                  f"g1={int(s['g1_success'])} g2={int(s['g2_success'])}", file=sys.stderr)
    print(f"wrote {n} episodes to {path}")


if __name__ == "__main__":
    main()
