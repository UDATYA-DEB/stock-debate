"""Run a debate agent and turn its output into stored claims.

The model is asked for JSON matching a schema (enforced server-side where
supported: Ollama and vLLM both accept `response_format` with a JSON schema).
If the output still doesn't parse, the agent gets one retry with the error.

Each LLM attempt is traced as a Langfuse generation linked to the prompt
version; the round's validation results are recorded as scores.
"""

from __future__ import annotations

import re
import time
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import ValidationError

from stockdebate.debate.casefile import CaseFile
from stockdebate.debate.prompts import opening_messages
from stockdebate.debate.schemas import ROLE_PREFIX, AgentTurn, Claim, OpeningOut, Role
from stockdebate.debate.validator import ClaimCheck, check_claims
from stockdebate.obs.tracing import Observability

MAX_ATTEMPTS = 2
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_ROLES = {"system": "system", "human": "user", "ai": "assistant"}


class ChatModel(Protocol):
    def bind(self, **kwargs: Any) -> "ChatModel": ...
    def invoke(self, messages: list[BaseMessage]) -> BaseMessage: ...


def extract_json(content: str) -> str:
    """Strip reasoning blocks and anything around the outermost JSON object."""
    content = _THINK.sub("", content)
    start, end = content.find("{"), content.rfind("}")
    return content[start:end + 1] if start != -1 and end > start else content


def _short_error(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'output'}: {e['msg']}" for e in exc.errors()[:5])


def _as_dicts(messages: list[BaseMessage]) -> list[dict]:
    return [{"role": _ROLES.get(m.type, m.type), "content": str(m.content)} for m in messages]


def _usage(reply: BaseMessage) -> dict[str, int] | None:
    usage = getattr(reply, "usage_metadata", None)
    if not usage:
        return None
    return {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}


def run_opening(role: Role, case: CaseFile, llm: ChatModel, model_name: str,
                obs: Observability | None = None) -> AgentTurn:
    obs = obs or Observability.disabled()
    messages, prompt = opening_messages(role, case, obs)
    schema = {"type": "json_schema",
              "json_schema": {"name": "opening", "schema": OpeningOut.model_json_schema()}}
    bound = llm.bind(response_format=schema)
    turn = AgentTurn(role=role, round=1, model=model_name,
                     prompt_tokens_est=sum(len(str(m.content)) for m in messages) // 4)

    start = time.monotonic()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        turn.attempts = attempt
        with obs.observe("llm-call", as_type="generation", model=model_name,
                         input=_as_dicts(messages), prompt=prompt.client,
                         metadata={"attempt": attempt, "prompt_source": prompt.source}) as gen:
            reply = bound.invoke(messages)
            content = str(reply.content)
            gen.update(output=content, usage_details=_usage(reply))
        turn.raw_outputs.append(content)
        try:
            parsed = OpeningOut.model_validate_json(extract_json(content))
        except ValidationError as exc:
            turn.error = f"invalid output: {_short_error(exc)}"
            messages = messages + [
                AIMessage(content=content),
                HumanMessage(content=f"Your reply was not valid: {_short_error(exc)}. "
                                     "Reply again with JSON only, matching the schema exactly."),
            ]
            continue
        turn.error = None
        turn.thesis = parsed.thesis
        turn.case_strength = parsed.case_strength
        prefix = ROLE_PREFIX[role]
        turn.claims = [
            Claim(id=f"{prefix}1-{i}", author=role, round=1, **c.model_dump())
            for i, c in enumerate(parsed.claims, start=1)
        ]
        break
    turn.latency_s = round(time.monotonic() - start, 1)
    turn.prompt_source = prompt.source
    return turn


def opening_round(role: Role, case: CaseFile, llm: ChatModel, model_name: str,
                  obs: Observability | None = None) -> tuple[AgentTurn, list[ClaimCheck]]:
    """Run one agent's opening, validate its claims, and record scores."""
    obs = obs or Observability.disabled()
    with obs.observe(f"opening:{role}", as_type="agent",
                     input={"symbol": case.symbol, "role": role, "model": model_name}) as span:
        turn = run_opening(role, case, llm, model_name, obs)
        checks = check_claims(turn.claims, case.sheet)
        failed = [c for c in checks if c.status != "supported"]
        span.update(output={
            "thesis": turn.thesis,
            "case_strength": turn.case_strength,
            "error": turn.error,
            "claims": [c.model_dump(exclude={"author", "round"}) for c in turn.claims],
            "checks": [c.model_dump() for c in checks],
        }, level="ERROR" if turn.error else "DEFAULT")
        span.score(name="valid_output", value=0.0 if turn.error else 1.0, data_type="NUMERIC")
        if checks:
            span.score(name="claims_supported_pct", data_type="NUMERIC",
                       value=round(100 * (len(checks) - len(failed)) / len(checks), 1))
            span.score(name="fabrications", value=float(len(failed)), data_type="NUMERIC",
                       comment="; ".join(f"{c.claim_id}: {c.detail}" for c in failed) or None)
    return turn, checks
