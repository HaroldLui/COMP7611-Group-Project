"""Model profiles (configs/models.toml) and API keys (.env)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "models.toml"
SECRET_HINTS = ("key", "token", "secret")


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines; existing environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_profile(name: str, path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    with open(path, "rb") as f:
        profiles = tomllib.load(f).get("profiles", {})
    if name not in profiles:
        raise SystemExit(f"profile {name!r} not found in {path}; available: {', '.join(profiles)}")
    return {"profile": name, **profiles[name]}


def public(profile: dict[str, Any]) -> dict[str, Any]:
    """Profile fields safe to write into result files (names of env vars are fine, values not)."""
    return {k: v for k, v in profile.items()
            if not any(h in k.lower() for h in SECRET_HINTS) or k.endswith("_env")}


def make_backend(profile: dict[str, Any]):
    from .llm import AnthropicBackend, FakeBackend

    kind = profile.get("backend", "fake")
    if kind == "fake":
        return FakeBackend()
    if kind == "anthropic":
        env = profile.get("api_key_env")
        if env and not os.environ.get(env):
            raise SystemExit(f"environment variable {env} is not set (put it in .env)")
        return AnthropicBackend(model=profile.get("model", "claude-opus-5-5"),
                                effort=profile.get("effort", "medium"),
                                max_tokens=profile.get("max_tokens", 16000))
    if kind == "openai":
        from .llm_openai import OpenAICompatBackend

        if "model" not in profile or "REPLACE" in profile["model"]:
            raise SystemExit(f"set `model` for profile {profile['profile']!r} in configs/models.toml")
        return OpenAICompatBackend(**{k: v for k, v in profile.items() if k not in ("backend", "profile")})
    raise SystemExit(f"unknown backend {kind!r} (use fake | anthropic | openai)")
