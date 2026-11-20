"""One agent = one tool-use loop. Logs every model call and tool call."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .env import TOOL_SPECS, Workspace
from .llm import Backend, Turn

MAX_STEPS = 12  # model calls per agent; same cap for every role and configuration


@dataclass
class AgentRun:
    role: str
    system: str
    messages: list[dict[str, Any]]
    tools: list[str]
    calls: list[dict[str, Any]] = field(default_factory=list)
    final_text: str = ""
    stop_reason: str = ""

    def log(self) -> dict[str, Any]:
        first = self.messages[0]["content"]
        return {"role": self.role, "system": self.system, "input": first, "tools": self.tools,
                "calls": self.calls, "final_text": self.final_text, "stop_reason": self.stop_reason}


def start(role: str, system: str, user_content: str, tools: list[str]) -> AgentRun:
    return AgentRun(role=role, system=system,
                    messages=[{"role": "user", "content": user_content}], tools=tools)


def step_until_done(run: AgentRun, backend: Backend, ws: Workspace) -> AgentRun:
    """Run the tool loop until the model stops calling tools (or the step cap is hit)."""
    specs = [TOOL_SPECS[t] for t in run.tools]
    for _ in range(MAX_STEPS):
        turn: Turn = backend.complete(run.system, run.messages, specs)
        run.messages.append({"role": "assistant", "content": turn.raw})
        uses = [b for b in turn.blocks if b["type"] == "tool_use"]
        results = []
        for u in uses:
            if u["name"] not in run.tools:
                out, err = f"Tool {u['name']!r} is not available to this agent.", True
            else:
                out, err = ws.call(run.role, u["name"], u["input"])
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": out,
                            **({"is_error": True} if err else {})})
        run.calls.append({"blocks": turn.blocks, "stop_reason": turn.stop_reason,
                          "model": turn.model, "usage": turn.usage,
                          "latency_s": round(turn.latency_s, 3),
                          "tool_results": [{"content": r["content"], "is_error": r.get("is_error", False)}
                                           for r in results]})
        run.stop_reason = turn.stop_reason
        if turn.stop_reason == "refusal" or not uses:
            run.final_text = "\n".join(b["text"] for b in turn.blocks if b["type"] == "text").strip()
            return run
        run.messages.append({"role": "user", "content": results})
    run.stop_reason = "max_steps"
    return run


def follow_up(run: AgentRun, backend: Backend, ws: Workspace, text: str) -> AgentRun:
    """Append a user message (e.g. a format-repair request) and continue the loop."""
    run.messages.append({"role": "user", "content": text})
    return step_until_done(run, backend, ws)
