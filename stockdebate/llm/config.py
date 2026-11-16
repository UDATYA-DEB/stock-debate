"""Runtime connection settings for the three models.

Values come from the setup screen, optionally pre-filled from a local `.env`
file. Secrets are never logged or written anywhere except `.env`, and only
when the user asks for that.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, set_key
from pydantic import BaseModel, SecretStr

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Defaults for the model names. Check current tags before relying on them.
DEFAULT_BULL_MODEL = "qwen3:8b"
DEFAULT_BEAR_MODEL = "gemma3:4b"
DEFAULT_JUDGE_MODEL = "gemini-2.5-flash"

DEFAULT_LANGFUSE_HOST = "https://cloud.langfuse.com"

PLACEHOLDERS = {
    "gemini_api_key": "AIzaSy...  (from Google AI Studio)",
    "bull_url": "http://localhost:11434",
    "bear_url": "https://your-tunnel.example.com",
    "bear_token": "token configured on the Kaggle side (optional)",
    "langfuse_public_key": "pk-lf-...",
    "langfuse_secret_key": "sk-lf-...",
    "langfuse_host": "https://cloud.langfuse.com  (or https://us.cloud.langfuse.com, or self-hosted)",
}


class RuntimeConfig(BaseModel):
    gemini_api_key: SecretStr
    judge_model: str = DEFAULT_JUDGE_MODEL
    bull_url: str
    bull_model: str = DEFAULT_BULL_MODEL
    bear_url: str
    bear_model: str = DEFAULT_BEAR_MODEL
    bear_token: SecretStr | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = DEFAULT_LANGFUSE_HOST

    @property
    def langfuse_secret(self) -> str | None:
        return self.langfuse_secret_key.get_secret_value() if self.langfuse_secret_key else None


_ENV_KEYS = {
    "gemini_api_key": "GEMINI_API_KEY",
    "judge_model": "JUDGE_MODEL",
    "bull_url": "BULL_URL",
    "bull_model": "BULL_MODEL",
    "bear_url": "BEAR_URL",
    "bear_model": "BEAR_MODEL",
    "bear_token": "BEAR_TOKEN",
    "langfuse_public_key": "LANGFUSE_PUBLIC_KEY",
    "langfuse_secret_key": "LANGFUSE_SECRET_KEY",
    "langfuse_host": "LANGFUSE_HOST",
}


def load_saved() -> dict[str, str]:
    """Values from .env (or the environment), keyed by RuntimeConfig field name."""
    file_values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    out = {}
    for field, env in _ENV_KEYS.items():
        value = file_values.get(env) or os.environ.get(env)
        if value:
            out[field] = value
    return out


def save(config: RuntimeConfig) -> Path:
    """Write the config to .env (local only; .env is git-ignored)."""
    ENV_FILE.touch(mode=0o600, exist_ok=True)
    for field, env in _ENV_KEYS.items():
        value = getattr(config, field)
        if value is None:
            continue
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        set_key(str(ENV_FILE), env, value, quote_mode="never")
    return ENV_FILE
