"""Configurations A, M1-M4 and the episode runner."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from . import agents, prompts
from .env import Scenario, Workspace
from .handoff import FREE_TEXT_SPEC, EmailPlan, ReaderNotes, json_spec, parse
from .llm import Backend


@dataclass(frozen=True)
class Config:
    name: str
    multi: bool
    handoff: str | None = None              # "text" | "json"
    executor_sees_request: bool | None = None


CONFIGS: dict[str, Config] = {
    "A": Config("A", multi=False),
    "M1": Config("M1", multi=True, handoff="text", executor_sees_request=False),
    "M2": Config("M2", multi=True, handoff="json", executor_sees_request=False),
    "M3": Config("M3", multi=True, handoff="text", executor_sees_request=True),
    "M4": Config("M4", multi=True, handoff="json", executor_sees_request=True),
}

MAX_REPAIRS = 1  # pre-registered: one repair attempt, then the episode is a format failure


def run_episode(sc: Scenario, cfg: Config, backend: Backend, gateway: bool) -> dict[str, Any]:
    ws = Workspace(sc, gateway=gateway)
    base = prompts.BASE.format(requester=sc.requester)
    record: dict[str, Any] = {"config": asdict(cfg), "gateway": gateway, "agents": [],
                              "handoffs": [], "status": "ok"}
    t0 = time.monotonic()
    try:
        if not cfg.multi:
            run = agents.start("single", prompts.SINGLE.format(base=base, requester=sc.requester),
                               sc.user_request, ["list_docs", "read_doc", "send_email"])
            record["agents"].append(agents.step_until_done(run, backend, ws).log())
        else:
            _run_pipeline(sc, cfg, backend, ws, base, record)
    except Exception as e:  # API errors etc.: keep the partial log, mark the episode
        record["status"] = "error"
        record["error"] = f"{type(e).__name__}: {e}"[:1000]
    record["events"] = ws.events
    record["wall_s"] = round(time.monotonic() - t0, 3)
    return record


def _run_pipeline(sc, cfg, backend, ws, base, record):
    fmt = cfg.handoff

    # Reader
    spec = FREE_TEXT_SPEC["reader"] if fmt == "text" else json_spec(ReaderNotes)
    reader = agents.start("reader", prompts.READER.format(base=base, requester=sc.requester,
                                                          format_spec=spec),
                          prompts.reader_input(sc.user_request), ["list_docs", "read_doc"])
    notes = _handoff(reader, backend, ws, fmt, ReaderNotes, "reader", "planner", record)
    if notes is None:
        return

    # Planner
    spec = FREE_TEXT_SPEC["planner"] if fmt == "text" else json_spec(EmailPlan)
    planner = agents.start("planner", prompts.PLANNER.format(base=base, format_spec=spec),
                           prompts.planner_input(sc.user_request, notes), [])
    plan = _handoff(planner, backend, ws, fmt, EmailPlan, "planner", "executor", record)
    if plan is None:
        return

    # Executor
    executor = agents.start(
        "executor", prompts.EXECUTOR.format(base=base),
        prompts.executor_input(plan, sc.user_request if cfg.executor_sees_request else None),
        ["send_email"])
    record["agents"].append(agents.step_until_done(executor, backend, ws).log())


def _handoff(run, backend, ws, fmt, model, src, dst, record) -> str | None:
    """Run an agent and return the message passed downstream (None = format failure)."""
    agents.step_until_done(run, backend, ws)
    h: dict[str, Any] = {"from": src, "to": dst, "format": fmt, "repairs": 0,
                         "raw": run.final_text, "content": None, "parse_ok": None, "error": None}
    if fmt == "text":
        h["content"] = run.final_text
    else:
        for attempt in range(MAX_REPAIRS + 1):
            try:
                obj = parse(model, run.final_text)
                # Re-serialize the validated object: downstream sees only schema fields.
                h["content"], h["parse_ok"] = obj.model_dump_json(indent=2), True
                break
            except ValueError as e:
                h["parse_ok"], h["error"] = False, str(e)
                if attempt < MAX_REPAIRS:
                    h["repairs"] += 1
                    agents.follow_up(run, backend, ws, prompts.REPAIR.format(error=str(e)[:300]))
        h["raw"] = run.final_text
    record["agents"].append(run.log())
    record["handoffs"].append(h)
    if h["content"] is None or (fmt == "text" and not h["content"]):
        record["status"] = "format_failure" if fmt == "json" else "empty_handoff"
        return None
    return h["content"]
