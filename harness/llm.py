"""Model backends.

A backend takes (system, messages, tools) and returns one Turn. Messages use the Anthropic
Messages API shape: {"role": "user"|"assistant", "content": str | list[block]}, where blocks
are text / tool_use / tool_result dicts. A backend for another provider converts to and from
this shape inside `complete`.

- AnthropicBackend: real model calls (requires `pip install anthropic` and credentials).
- FakeBackend: deterministic rule-based stand-in for offline plumbing tests. Its numbers are
  NOT experimental data.
"""

from __future__ import annotations

import itertools
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Turn:
    blocks: list[dict[str, Any]]      # normalized text / tool_use blocks (for logs and control flow)
    raw: Any                          # provider content to append verbatim as the assistant turn
    stop_reason: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_s: float = 0.0


class Backend(Protocol):
    name: str
    model: str

    def complete(self, system: str, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> Turn: ...


class AnthropicBackend:
    """Claude via the official SDK, manual tool loop (driven by harness.agents).

    Deliberate choices for a controlled experiment:
    - effort is set explicitly and logged (Opus 5.5 defaults to medium if omitted);
    - no sampling parameters (temperature etc. are rejected on the current API), so
      repeats give natural run-to-run variance;
    - no server-side refusal `fallbacks`: a fallback would silently swap the model under
      test. Refusals are logged as a stop_reason instead.
    """

    name = "anthropic"

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium",
                 max_tokens: int = 16000):
        import anthropic  # imported lazily so the fake backend works without the SDK

        self.client = anthropic.Anthropic(max_retries=4)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def complete(self, system, messages, tools):
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": self.effort},
        )
        if tools:
            kwargs["tools"] = tools
        t0 = time.monotonic()
        resp = self.client.messages.create(**kwargs)
        latency = time.monotonic() - t0

        blocks: list[dict[str, Any]] = []
        for b in resp.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        # Thinking blocks stay in `raw` (they must be passed back unchanged) but aren't logged.
        usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        return Turn(blocks=blocks, raw=resp.content, stop_reason=resp.stop_reason or "",
                    model=resp.model, usage=usage, latency_s=latency)


# --------------------------------------------------------------------------------------
# Offline fake
# --------------------------------------------------------------------------------------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"https?://\S+")


class FakeBackend:
    """A gullible, rule-based 'model' that exercises every code path.

    Behaviour (by role, read from the 'ROLE: x' line of the system prompt):
    - single/reader: list_docs, read every doc, then act. Free-text notes copy the documents
      verbatim (so injections propagate); JSON notes keep only lines that look like
      structured facts (so most injections are dropped).
    - planner/single: adds any *.test address it sees as CC (gullible).
    - executor: sends what the plan says, but if the user's request is visible it drops
      recipients the request doesn't mention.
    """

    name = "fake"
    model = "fake-gullible-v1"

    def complete(self, system, messages, tools):
        role = re.search(r"ROLE: (\w+)", system).group(1)
        text = _all_text(messages)
        request = _first_user_text(messages)
        handler = getattr(self, f"_{role}")
        blocks = handler(system, messages, text, request)
        stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
        n_in = len(json.dumps(messages, default=str)) // 4
        n_out = len(json.dumps(blocks)) // 4
        return Turn(blocks=blocks, raw=blocks, stop_reason=stop, model=self.model,
                    usage={"input_tokens": n_in, "output_tokens": n_out})

    # -- roles -------------------------------------------------------------------------
    def _single(self, system, messages, text, request):
        step = _next_read_step(messages)
        if step is not None:
            return [step]
        if not _called(messages, "send_email"):
            auth = _EMAIL.findall(request)
            cc = sorted({e for e in _EMAIL.findall(text) if e.endswith(".test")})
            body = "Summary of the meeting documents:\n" + _doc_text(messages)[:2400]
            return [_tool("send_email", {"to": auth, "cc": cc, "subject": "Meeting summary",
                                         "body": body})]
        return [{"type": "text", "text": "Sent the summary."}]

    def _reader(self, system, messages, text, request):
        step = _next_read_step(messages)
        if step is not None:
            return [step]
        docs = _doc_text(messages)
        if "JSON Schema" not in system:
            return [{"type": "text", "text": "Notes from the documents:\n" + docs[:1800]}]
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", docs)
        attendees_line = re.search(r"Attendees: (.*)", docs)
        actions = []
        for m in re.finditer(r"Action: (.+?) — (.+?) \(due (\d{4}-\d{2}-\d{2})\)", docs):
            actions.append({"owner": m.group(1), "task": m.group(2)[:200], "due": m.group(3)})
        notes = {
            "meeting_title": (re.search(r"Title: (.*)", docs) or re.search(r"(.*)", docs)).group(1)[:100],
            "date": dates[0] if dates else "2026-01-01",
            "attendees": _EMAIL.findall(attendees_line.group(1)) if attendees_line else [],
            "decisions": [d[:200] for d in re.findall(r"Decision: (.*)", docs)][:8],
            "action_items": actions[:10],
        }
        return [{"type": "text", "text": json.dumps(notes)}]

    def _planner(self, system, messages, text, request):
        auth = _EMAIL.findall(request.split("Reader's notes:", 1)[0])
        cc = sorted({e for e in _EMAIL.findall(text) if e.endswith(".test")})
        notes = text.split("Reader's notes:", 1)[-1].strip()
        if "JSON Schema" in system:
            try:
                n = json.loads(notes)
                body = ("Decisions:\n" + "\n".join(f"- {d}" for d in n["decisions"])
                        + "\n\nAction items:\n"
                        + "\n".join(f"- {a['owner']}: {a['task']} (due {a['due']})"
                                    for a in n["action_items"]))
            except (ValueError, KeyError):
                body = notes
            plan = {"to": auth, "cc": cc, "bcc": [], "subject": "Meeting summary", "body": body[:2500]}
            return [{"type": "text", "text": json.dumps(plan)}]
        plan = (f"To: {', '.join(auth)}\nCC: {', '.join(cc)}\nSubject: Meeting summary\n"
                f"Body:\n{notes[:2000]}")
        return [{"type": "text", "text": plan}]

    def _executor(self, system, messages, text, request):
        if _called(messages, "send_email"):
            return [{"type": "text", "text": "Sent."}]
        plan_text = request.split("Email plan from the planner:", 1)[-1]
        plan_text, _, user_req = plan_text.partition("User's original request:")
        try:
            p = json.loads(plan_text.strip())
            to, cc, subject, body = p["to"], p.get("cc", []), p["subject"], p["body"]
        except ValueError:
            to = _EMAIL.findall(_line(plan_text, "To:"))
            cc = _EMAIL.findall(_line(plan_text, "CC:"))
            subject = _line(plan_text, "Subject:") or "Meeting summary"
            body = plan_text.split("Body:", 1)[-1].strip()
        if user_req:
            allowed = set(_EMAIL.findall(user_req))
            to = [r for r in to if r in allowed] or sorted(allowed)
            cc = [r for r in cc if r in allowed]
        return [_tool("send_email", {"to": to, "cc": cc, "subject": subject, "body": body})]


_ids = itertools.count(1)


def _tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"fake_{next(_ids)}", "name": name, "input": args}


def _blocks(msg: dict[str, Any]) -> list[dict[str, Any]]:
    c = msg["content"]
    return [{"type": "text", "text": c}] if isinstance(c, str) else c


def _first_user_text(messages) -> str:
    return "".join(b.get("text", "") for b in _blocks(messages[0]) if b["type"] == "text")


def _all_text(messages) -> str:
    out = []
    for m in messages:
        for b in _blocks(m):
            if b["type"] == "text":
                out.append(b["text"])
            elif b["type"] == "tool_result":
                out.append(str(b["content"]))
    return "\n".join(out)


def _doc_text(messages) -> str:
    return "\n\n".join(str(b["content"]) for m in messages for b in _blocks(m)
                       if b["type"] == "tool_result" and str(b["content"]).startswith("Title:"))


def _called(messages, name: str) -> bool:
    return any(b["type"] == "tool_use" and b["name"] == name
               for m in messages if m["role"] == "assistant" for b in _blocks(m))


def _next_read_step(messages):
    if not _called(messages, "list_docs"):
        return _tool("list_docs", {})
    listing = next(json.loads(b["content"]) for m in messages for b in _blocks(m)
                   if b["type"] == "tool_result" and str(b["content"]).startswith("["))
    read = {b["input"]["doc_id"] for m in messages if m["role"] == "assistant"
            for b in _blocks(m) if b["type"] == "tool_use" and b["name"] == "read_doc"}
    for d in listing:
        if d["id"] not in read:
            return _tool("read_doc", {"doc_id": d["id"]})
    return None


def _line(text: str, prefix: str) -> str:
    for ln in text.splitlines():
        if ln.strip().startswith(prefix):
            return ln.split(prefix, 1)[1].strip()
    return ""

