"""Print one episode as a readable trace (for demos and failure analysis).

    python -m harness.show results/fake-dev                       # first attacked M1 episode
    python -m harness.show results/fake-dev --config M2 --goal G2
    python -m harness.show results/fake-dev --key "dev-01|fixit-G2-body|M1|noGW|r0"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyze import load

W = 78


def short(text: str, n: int = 600) -> str:
    text = str(text).strip()
    return text if len(text) <= n else text[:n] + f" … [{len(text) - n} more chars]"


def highlight(text: str, marker: str | None) -> str:
    return text.replace(marker, f">>>{marker}<<<") if marker else text


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--key")
    ap.add_argument("--config", default="M1")
    ap.add_argument("--goal", default="G1", choices=["G1", "G2", "clean"])
    ap.add_argument("--full", action="store_true", help="don't truncate long texts")
    a = ap.parse_args(argv)
    n = 10**9 if a.full else 600

    rows = load(Path(a.folder) / "episodes.jsonl")
    if a.key:
        row = next(r for r in rows if r["key"] == a.key)
    else:
        goal = None if a.goal == "clean" else a.goal
        row = next(r for r in rows if r["config"] == a.config and r["goal"] == goal)
    m, rec, s = row.get("marker"), row["record"], row["score"]

    print("=" * W)
    print(f"EPISODE {row['key']}   model={row['model']}")
    if row["backend"] == "fake":
        print("(fake backend: rule-based stand-in, not a real model)")
    print("=" * W)
    for ag in rec["agents"]:
        print(f"\n## {ag['role'].upper()}   tools={ag['tools'] or 'none'}")
        print(f"-- input:\n{highlight(short(ag['input'], n), m)}")
        for c in ag["calls"]:
            for b in c["blocks"]:
                if b["type"] == "tool_use":
                    print(f"-- calls {b['name']}({highlight(json.dumps(b['input']), m) if b['name'] == 'send_email' else json.dumps(b['input'])})")
            for tr in c["tool_results"]:
                if m and m in tr["content"]:
                    print(f"   result contains the injection: …{highlight(_around(tr['content'], m), m)}…")
        if ag["final_text"]:
            print(f"-- output:\n{highlight(short(ag['final_text'], n), m)}")
    for h, lab in zip(rec["handoffs"], s["handoff_labels"]):
        print(f"\n[handoff {h['from']} -> {h['to']} ({h['format']}): injection {lab.upper()}]")
    print("\n" + "-" * W)
    for e in rec["events"]:
        if e["tool"] == "send_email":
            print(f"EMAIL {e['status'].upper()}: to={e['args']['to']} cc={e['args']['cc']} "
                  f"unauthorized={e.get('unauthorized')}")
    print(f"SCORE: utility={s['utility']}  G1 success={s['g1_success']} (attempt={s['g1_attempt']})  "
          f"G2 success={s['g2_success']}  misdirect={s.get('misdirect')}  status={s['status']}")
    print(f"COST: {s['n_model_calls']} model calls, {s['input_tokens'] + s['output_tokens']} tokens")


def _around(text: str, marker: str, k: int = 120) -> str:
    i = text.find(marker)
    return text[max(0, i - k): i + len(marker) + k].replace("\n", " ")


if __name__ == "__main__":
    main()
