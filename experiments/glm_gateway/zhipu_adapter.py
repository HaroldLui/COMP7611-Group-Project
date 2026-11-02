"""Pilot-only adapter retaining opaque provider reasoning inside each agent session.

The original task prompts, handoff schemas, tools and scoring remain unchanged.
Opaque reasoning is returned only to the provider; it is not passed to other agents.
"""
from __future__ import annotations

import json
import time

from harness.llm import Turn
from harness.llm_openai import OpenAICompatBackend, _FINISH, to_chat_messages

OPAQUE_TYPE = "provider_reasoning"


def to_zhipu_messages(system, messages):
    converted = to_chat_messages(system, messages)
    assistants = iter(m for m in converted if m["role"] == "assistant")
    for original in messages:
        if original["role"] != "assistant":
            continue
        target = next(assistants)
        if isinstance(original["content"], list):
            reasoning = [b["text"] for b in original["content"] if b["type"] == OPAQUE_TYPE]
            if reasoning:
                target["reasoning_content"] = "".join(reasoning)
    return converted


class ZhipuPilotBackend(OpenAICompatBackend):
    def complete(self, system, messages, tools):
        kwargs = dict(model=self.model, messages=to_zhipu_messages(system, messages), **self.params)
        if tools:
            kwargs["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
                for t in tools]
        started = time.monotonic()
        response = self.client.chat.completions.create(**kwargs)
        elapsed = time.monotonic() - started
        self.last_provider_metadata = {
            "request_id": response.id if hasattr(response, "id") else None,
            "usage": response.usage.model_dump() if hasattr(response.usage, "model_dump") else None}
        choice = response.choices[0]
        message = choice.message
        blocks = []
        if message.content:
            blocks.append({"type": "text", "text": message.content})
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"_unparseable_arguments": call.function.arguments}
            blocks.append({"type": "tool_use", "id": call.id,
                           "name": call.function.name, "input": arguments})
        raw = list(blocks)
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            raw.append({"type": OPAQUE_TYPE, "text": reasoning})
        usage = response.usage
        counts = ({"input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                   "output_tokens": getattr(usage, "completion_tokens", 0) or 0} if usage else {})
        return Turn(blocks=blocks, raw=raw,
                    stop_reason=_FINISH.get(choice.finish_reason or "", choice.finish_reason or ""),
                    model=response.model or self.model, usage=counts, latency_s=elapsed)


def log_snapshot(value):
    """Keep hashes/lengths of opaque provider content instead of its text in disk logs."""
    import hashlib
    if isinstance(value, dict):
        if value.get("type") == OPAQUE_TYPE:
            text = value["text"]
            return {"type": OPAQUE_TYPE, "omitted_from_disk": True, "characters": len(text),
                    "sha256": hashlib.sha256(text.encode()).hexdigest()}
        return {key: log_snapshot(item) for key, item in value.items()}
    if isinstance(value, list):
        return [log_snapshot(item) for item in value]
    return value
