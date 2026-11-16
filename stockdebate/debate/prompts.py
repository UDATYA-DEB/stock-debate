"""Build the messages for a debate agent from the managed prompt."""

from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from stockdebate.debate.casefile import CaseFile, render_casefile
from stockdebate.debate.prompt_defaults import OPENING_PROMPT
from stockdebate.debate.schemas import Role
from stockdebate.obs.tracing import Observability, PromptHandle

_TYPES = {"system": SystemMessage, "user": HumanMessage}


def to_langchain(messages: list[dict]) -> list[BaseMessage]:
    return [_TYPES[m["role"]](content=m["content"]) for m in messages]


def opening_messages(role: Role, case: CaseFile, obs: Observability) -> tuple[list[BaseMessage], PromptHandle]:
    prompt = obs.prompt(OPENING_PROMPT)
    compiled = prompt.compile(
        stance=prompt.config["stance"][role],
        company=case.name,
        symbol=case.symbol,
        casefile=render_casefile(case),
    )
    return to_langchain(compiled), prompt
