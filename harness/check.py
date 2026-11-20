"""Check that a model profile works before spending money on a run (2-3 small API calls).

    python -m harness.check --profile deepseek

It runs the executor role on a fixed plan and checks that the model (1) answers, (2) calls
the send_email tool with the right recipient, and (3) continues correctly after a tool result.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import agents, prompts
from .config import ROOT, load_dotenv, load_profile, make_backend
from .env import Workspace, load_scenarios


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    load_dotenv()
    profile = load_profile(a.profile, *([Path(a.config)] if a.config else []))
    backend = make_backend(profile)

    sc = load_scenarios(str(ROOT / "data" / "scenarios.json"))[0]
    to = sc.authorized[0]
    plan = f"To: {to}\nSubject: Connection test\nBody:\nThis is a test of the email tool."
    ws = Workspace(sc)
    run = agents.start("executor", prompts.EXECUTOR.format(base=prompts.BASE.format(requester=sc.requester)),
                       prompts.executor_input(plan, None), ["send_email"])
    try:
        agents.step_until_done(run, backend, ws)
    except Exception as e:
        print(f"FAIL: request error: {type(e).__name__}: {e}")
        return 1

    sent = [e for e in ws.events if e["tool"] == "send_email"]
    tokens = sum(c["usage"].get("input_tokens", 0) + c["usage"].get("output_tokens", 0) for c in run.calls)
    print(f"profile={a.profile} backend={backend.name} model={backend.model}")
    print(f"model calls={len(run.calls)} tokens={tokens} "
          f"latency={sum(c['latency_s'] for c in run.calls):.1f}s stop={run.stop_reason}")
    ok = True
    if not sent:
        print("FAIL: the model never called send_email; it may not support tool calling, "
              "or needs different settings.")
        ok = False
    elif to not in [r.lower() for r in sent[0]["args"]["to"]]:
        print(f"FAIL: send_email called with to={sent[0]['args']['to']} (expected {to})")
        ok = False
    else:
        print("OK: tool call made with the right recipient.")
    if run.stop_reason not in ("end_turn", "stop"):
        print(f"WARN: last stop reason was {run.stop_reason!r} (expected the model to finish)")
    print(f"final reply: {run.final_text[:200]!r}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
