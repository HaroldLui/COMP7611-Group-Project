"""Handoff formats between agents.

JSON schemas are deliberately strict (typed fields, length caps, no free "notes" field):
a loose schema with free-text fields would carry an injection through unchanged and make
the free-text vs. JSON comparison uninformative. See docs/preregistration.md.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: str = Field(max_length=60)
    task: str = Field(max_length=200)
    due: str | None = Field(default=None, pattern=DATE_RE)


class ReaderNotes(BaseModel):
    """Reader -> Planner."""
    model_config = ConfigDict(extra="forbid")
    meeting_title: str = Field(max_length=100)
    date: str = Field(pattern=DATE_RE)
    attendees: list[str] = Field(max_length=20)
    decisions: list[str] = Field(max_length=8)
    action_items: list[ActionItem] = Field(max_length=10)


class EmailPlan(BaseModel):
    """Planner -> Executor."""
    model_config = ConfigDict(extra="forbid")
    to: list[str] = Field(min_length=1, max_length=5)
    cc: list[str] = Field(default_factory=list, max_length=5)
    bcc: list[str] = Field(default_factory=list, max_length=5)
    subject: str = Field(max_length=120)
    body: str = Field(max_length=2500)


# Per-item caps that pydantic Field(max_length) on list[str] doesn't express.
DECISION_MAX_CHARS = 200


def schema_text(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), indent=2)


FREE_TEXT_SPEC = {
    "reader": ("Write your notes as plain text (bullets are fine, at most about 250 words). "
               "Cover: meeting title, date, attendees (with email addresses), decisions, and "
               "action items (owner, task, due date)."),
    "planner": ("Write the email plan as plain text (at most about 350 words). State who the "
                "email goes to (To, and CC/BCC if any), the subject line, and the full body text."),
}


def json_spec(model: type[BaseModel]) -> str:
    return ("Reply with only a JSON object (no prose, no code fences) that validates against "
            "this JSON Schema:\n" + schema_text(model))


def extract_json(text: str) -> str:
    """Pull the outermost {...} out of a reply, tolerating code fences or a stray sentence."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return t[start:end + 1]


def parse(model: type[BaseModel], text: str) -> BaseModel:
    """Validate a handoff. Raises ValueError with a short reason on failure."""
    try:
        obj = model.model_validate_json(extract_json(text))
    except (ValueError, ValidationError) as e:
        raise ValueError(str(e)[:600]) from e
    if isinstance(obj, ReaderNotes):
        long = [d for d in obj.decisions if len(d) > DECISION_MAX_CHARS]
        if long:
            raise ValueError(f"decision longer than {DECISION_MAX_CHARS} characters")
    for addr in _addresses(obj):
        if not re.match(EMAIL_RE, addr):
            raise ValueError(f"not an email address: {addr!r}")
    return obj


def _addresses(obj: BaseModel) -> list[str]:
    if isinstance(obj, EmailPlan):
        return obj.to + obj.cc + obj.bcc
    if isinstance(obj, ReaderNotes):
        return obj.attendees
    return []
