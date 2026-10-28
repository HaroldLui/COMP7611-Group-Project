"""Backend for any OpenAI-compatible Chat Completions endpoint.

Covers OpenAI, DeepSeek, Qwen (DashScope), Gemini's OpenAI-compatible endpoint, OpenRouter,
and local servers (Ollama, vLLM, LM Studio). The model must support function/tool calling.

The harness keeps history in the Anthropic-style block format (see harness/llm.py); this
module converts that history to Chat Completions messages on every call.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from .llm import Turn

_FINISH = {"tool_calls": "tool_use", "stop": "end_turn", "length": "max_tokens",
           "content_filter": "refusal", "function_call": "tool_use"}


class OpenAICompatBackend:
    name = "openai"

    def __init__(self, model: str, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY",
                 temperature: float | None = None, max_tokens: int = 4096,
                 max_tokens_param: str = "max_tokens", reasoning_effort: str | None = None,
                 seed: int | None = None, extra_body: dict[str, Any] | None = None,
                 timeout: float = 120.0, **_ignored):
        import openai  # lazy: only needed when this backend is used

        key = os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"environment variable {api_key_env} is not set (put it in .env)")
        self.client = openai.OpenAI(api_key=key, base_url=base_url, timeout=timeout, max_retries=4)
        self.model = model
        self.effort = reasoning_effort
        self.params: dict[str, Any] = {max_tokens_param: max_tokens}
        if temperature is not None:
            self.params["temperature"] = temperature
        if reasoning_effort is not None:
            self.params["reasoning_effort"] = reasoning_effort
        if seed is not None:
            self.params["seed"] = seed
        if extra_body:
            self.params["extra_body"] = extra_body

    def complete(self, system, messages, tools):
        kwargs: dict[str, Any] = dict(model=self.model, messages=to_chat_messages(system, messages),
                                      **self.params)
        if tools:
            kwargs["tools"] = [{"type": "function",
                                "function": {"name": t["name"], "description": t["description"],
                                             "parameters": t["input_schema"]}} for t in tools]
        t0 = time.monotonic()
        resp = self.client.chat.completions.create(**kwargs)
        latency = time.monotonic() - t0

        choice = resp.choices[0]
        msg = choice.message
        blocks: list[dict[str, Any]] = []
        if msg.content:
            blocks.append({"type": "text", "text": msg.content})
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_unparseable_arguments": tc.function.arguments}
            blocks.append({"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args})
        stop = _FINISH.get(choice.finish_reason or "", choice.finish_reason or "")
        u = resp.usage
        usage = {"input_tokens": getattr(u, "prompt_tokens", 0) or 0,
                 "output_tokens": getattr(u, "completion_tokens", 0) or 0} if u else {}
        return Turn(blocks=blocks, raw=blocks, stop_reason=stop, model=resp.model or self.model,
                    usage=usage, latency_s=latency)


def to_chat_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        if m["role"] == "assistant":
            text = "\n".join(b["text"] for b in content if b["type"] == "text")
            calls = [{"id": b["id"], "type": "function",
                      "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                     for b in content if b["type"] == "tool_use"]
            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:
            for b in content:
                if b["type"] == "tool_result":
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"],
                                "content": str(b["content"])})
            texts = [b["text"] for b in content if b["type"] == "text"]
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
    return out
