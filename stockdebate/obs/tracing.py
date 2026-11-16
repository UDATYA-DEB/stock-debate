"""Observability (Langfuse): traces, prompt management, scores.

`Observability` wraps a Langfuse client, or does nothing when Langfuse isn't
configured, so the rest of the code never needs `if langfuse:` checks.

Trace layout for a run:
  trace (session = run id, tags = symbol, role)
    └ agent span "opening:bull"          ← scores: claims_supported_pct, fabrications
        └ generation "llm-call" (per attempt, linked to the prompt version)
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel

from stockdebate.debate.prompt_defaults import DEFAULT_PROMPTS

_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class _NoOp:
    """Stands in for a Langfuse span/generation when tracing is off."""

    def update(self, **kwargs: Any) -> "_NoOp":
        return self

    def score(self, **kwargs: Any) -> None:
        return None


class PromptHandle(BaseModel, arbitrary_types_allowed=True):
    name: str
    source: str  # "langfuse vN" or "built-in"
    messages: list[dict]  # templates, with {{variables}}
    config: dict
    client: Any = None  # Langfuse prompt client, used to link generations to the version

    def compile(self, **variables: str) -> list[dict]:
        def fill(text: str) -> str:
            return _VAR.sub(lambda m: str(variables.get(m.group(1), m.group(0))), text)
        return [{"role": m["role"], "content": fill(m["content"])} for m in self.messages]


class Observability:
    def __init__(self, client: Any = None):
        self.client = client  # langfuse.Langfuse or None

    @classmethod
    def disabled(cls) -> "Observability":
        return cls(None)

    @classmethod
    def from_keys(cls, public_key: str | None, secret_key: str | None, host: str | None) -> "Observability":
        if not (public_key and secret_key):
            return cls.disabled()
        from langfuse import Langfuse
        return cls(Langfuse(public_key=public_key, secret_key=secret_key, base_url=host or None))

    @property
    def enabled(self) -> bool:
        return self.client is not None

    # ---------- prompts ----------

    def prompt(self, name: str) -> PromptHandle:
        """The production version from Langfuse, or the built-in default."""
        default = DEFAULT_PROMPTS[name]
        if self.enabled:
            try:
                p = self.client.get_prompt(name, type="chat", label="production",
                                           cache_ttl_seconds=60, max_retries=1)
                return PromptHandle(
                    name=name,
                    source=f"langfuse v{p.version}",
                    messages=[{"role": m["role"], "content": m["content"]} for m in p.prompt],
                    config=p.config or default["config"],
                    client=p,
                )
            except Exception:
                pass  # unreachable or missing: fall back to the built-in prompt
        return PromptHandle(name=name, source="built-in", messages=default["messages"],
                            config=default["config"])

    def missing_prompts(self) -> list[str]:
        if not self.enabled:
            return []
        missing = []
        for name in DEFAULT_PROMPTS:
            try:
                self.client.get_prompt(name, type="chat", label="production",
                                       cache_ttl_seconds=0, max_retries=0)
            except Exception:
                missing.append(name)
        return missing

    def push_default_prompts(self) -> list[str]:
        """Create prompts that don't exist in Langfuse yet. Never overwrites existing ones."""
        pushed = []
        for name in self.missing_prompts():
            default = DEFAULT_PROMPTS[name]
            self.client.create_prompt(name=name, type="chat", prompt=default["messages"],
                                      config=default["config"], labels=["production"],
                                      commit_message="Initial version from stockdebate defaults")
            pushed.append(name)
        return pushed

    # ---------- tracing ----------

    @contextmanager
    def trace(self, name: str, session_id: str, tags: list[str], metadata: dict | None = None) -> Iterator[Any]:
        """Root of a trace; everything observed inside it is grouped under it."""
        if not self.enabled:
            yield _NoOp()
            return
        from langfuse import propagate_attributes
        with propagate_attributes(trace_name=name, session_id=session_id, tags=tags,
                                  metadata={k: str(v) for k, v in (metadata or {}).items()}):
            with self.client.start_as_current_observation(name=name, as_type="chain") as root:
                yield root

    @contextmanager
    def observe(self, name: str, as_type: str = "span", **kwargs: Any) -> Iterator[Any]:
        if not self.enabled:
            yield _NoOp()
            return
        if kwargs.get("prompt") is None:
            kwargs.pop("prompt", None)
        with self.client.start_as_current_observation(name=name, as_type=as_type, **kwargs) as obs:
            yield obs

    def flush(self) -> None:
        if self.enabled:
            self.client.flush()
