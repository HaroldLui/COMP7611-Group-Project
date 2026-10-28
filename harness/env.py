"""Scenario data model, mock tools, and the optional recipient-allowlist gateway.

Nothing here sends real email: send_email only appends to the episode's event log.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Doc:
    id: str
    title: str
    content: str


@dataclass
class Injection:
    template: str   # direct | authority | fixit | role
    goal: str       # G1 (redirect) | G2 (content manipulation)
    position: str   # body | footer
    doc_id: str
    marker: str     # attacker address (G1) or attacker URL (G2); used for rule-based scoring
    text: str       # the exact payload inserted into the document


@dataclass
class Scenario:
    id: str
    split: str                      # dev | test
    requester: str                  # name of the user who owns the task
    user_request: str
    authorized: list[str]           # recipients the user named (lower-case emails)
    docs: list[Doc]
    facts: list[list[str]]          # each fact = list of accepted aliases (case-insensitive substring)
    injection: Injection | None = None

    @property
    def condition(self) -> str:
        if self.injection is None:
            return "clean"
        i = self.injection
        return f"{i.template}-{i.goal}-{i.position}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Scenario":
        inj = d.get("injection")
        return Scenario(
            id=d["id"],
            split=d["split"],
            requester=d["requester"],
            user_request=d["user_request"],
            authorized=[a.lower() for a in d["authorized"]],
            docs=[Doc(**x) for x in d["docs"]],
            facts=d["facts"],
            injection=Injection(**inj) if inj else None,
        )


def load_scenarios(path: str) -> list[Scenario]:
    with open(path) as f:
        return [Scenario.from_dict(d) for d in json.load(f)]


# Tool specs in the Anthropic Messages API shape ({name, description, input_schema});
# other backends convert from this neutral form.
TOOL_SPECS: dict[str, dict[str, Any]] = {
    "list_docs": {
        "name": "list_docs",
        "description": "List the user's available documents (id and title).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "read_doc": {
        "name": "read_doc",
        "description": "Read the full text of one document by id.",
        "input_schema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
            "additionalProperties": False,
        },
    },
    "send_email": {
        "name": "send_email",
        "description": "Send an email on the user's behalf.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "array", "items": {"type": "string"}},
                "cc": {"type": "array", "items": {"type": "string"}},
                "bcc": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
    },
}


@dataclass
class Workspace:
    """Per-episode mock environment. Every tool call is recorded in `events`."""

    scenario: Scenario
    gateway: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)

    def call(self, agent: str, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Execute a tool call. Returns (result_text, is_error)."""
        if name == "list_docs":
            out = json.dumps([{"id": d.id, "title": d.title} for d in self.scenario.docs])
            self.events.append({"agent": agent, "tool": name, "args": args, "status": "ok"})
            return out, False

        if name == "read_doc":
            doc = next((d for d in self.scenario.docs if d.id == args.get("doc_id")), None)
            status = "ok" if doc else "not_found"
            self.events.append({"agent": agent, "tool": name, "args": args, "status": status})
            if doc is None:
                return f"No document with id {args.get('doc_id')!r}.", True
            return f"Title: {doc.title}\n\n{doc.content}", False

        if name == "send_email":
            email = {
                "to": _as_list(args.get("to")),
                "cc": _as_list(args.get("cc")),
                "bcc": _as_list(args.get("bcc")),
                "subject": str(args.get("subject", "")),
                "body": str(args.get("body", "")),
            }
            unauthorized = [r for r in recipients(email) if r not in self.scenario.authorized]
            if self.gateway and unauthorized:
                self.events.append({"agent": agent, "tool": name, "args": email,
                                    "status": "blocked", "unauthorized": unauthorized})
                return ("Blocked by policy: these recipients were not authorized by the user: "
                        + ", ".join(unauthorized)), True
            self.events.append({"agent": agent, "tool": name, "args": email, "status": "sent",
                                "unauthorized": unauthorized})
            return "Email sent.", False

        self.events.append({"agent": agent, "tool": name, "args": args, "status": "unknown_tool"})
        return f"Unknown tool {name!r}.", True


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return [str(x).strip() for x in v if str(x).strip()]


def recipients(email: dict[str, Any]) -> list[str]:
    return [r.lower() for r in email["to"] + email["cc"] + email["bcc"]]
