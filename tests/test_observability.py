"""Langfuse integration with a fake client (no network)."""

from types import SimpleNamespace

from stockdebate.debate.agent import opening_round
from stockdebate.debate.prompt_defaults import OPENING_CONFIG, OPENING_MESSAGES, OPENING_PROMPT
from stockdebate.debate.prompts import opening_messages
from stockdebate.llm.health import check_langfuse
from stockdebate.obs.tracing import Observability
from tests.test_debate_opening import GOOD_OPENING, FakeLLM, case


class FakeLangfuse:
    def __init__(self, prompts=None, auth=True):
        self.prompts = dict(prompts or {})
        self.auth = auth
        self.created = []

    def auth_check(self):
        return self.auth

    def get_prompt(self, name, **kwargs):
        if name not in self.prompts:
            raise LookupError(f"prompt {name} not found")
        return self.prompts[name]

    def create_prompt(self, **kwargs):
        self.created.append(kwargs)
        self.prompts[kwargs["name"]] = SimpleNamespace(version=1, prompt=kwargs["prompt"],
                                                       config=kwargs["config"])

    def flush(self):
        pass


def edited_prompt():
    messages = [dict(m) for m in OPENING_MESSAGES]
    messages[0]["content"] = "EDITED IN LANGFUSE: you are {{stance}} on {{symbol}}."
    return SimpleNamespace(version=3, prompt=messages, config=OPENING_CONFIG)


def test_prompt_fetched_from_langfuse():
    obs = Observability(FakeLangfuse({OPENING_PROMPT: edited_prompt()}))
    messages, prompt = opening_messages("bear", case(), obs)
    assert prompt.source == "langfuse v3"
    assert messages[0].content.startswith("EDITED IN LANGFUSE: you are the BEAR analyst")
    assert "TEST" in messages[0].content


def test_falls_back_to_built_in_prompt():
    for obs in (Observability.disabled(), Observability(FakeLangfuse())):  # off, or prompt missing
        messages, prompt = opening_messages("bull", case(), obs)
        assert prompt.source == "built-in"
        assert "BULL analyst" in messages[0].content
        assert "{{" not in messages[0].content + messages[1].content


def test_push_creates_only_missing_prompts():
    client = FakeLangfuse()
    obs = Observability(client)
    assert obs.missing_prompts() == [OPENING_PROMPT]
    assert obs.push_default_prompts() == [OPENING_PROMPT]
    assert client.created[0]["labels"] == ["production"]
    assert obs.push_default_prompts() == []  # second time: nothing to do, nothing overwritten
    assert len(client.created) == 1


def test_langfuse_health():
    assert check_langfuse(None, None, None).ok  # optional
    assert not check_langfuse("pk-lf-...", "sk-lf-...", None).ok  # placeholders
    assert not check_langfuse("pk", None, None).ok  # half-configured

    def factory(client):
        return lambda *a: Observability(client)

    bad = check_langfuse("pk", "sk", "h", obs_factory=factory(FakeLangfuse(auth=False)))
    assert not bad.ok and "rejected" in bad.detail
    missing = check_langfuse("pk", "sk", "h", obs_factory=factory(FakeLangfuse()))
    assert not missing.ok and missing.available_models == [OPENING_PROMPT]
    good = check_langfuse("pk", "sk", "h",
                          obs_factory=factory(FakeLangfuse({OPENING_PROMPT: edited_prompt()})))
    assert good.ok


def test_opening_round_without_langfuse_still_validates():
    turn, checks = opening_round("bull", case(), FakeLLM(GOOD_OPENING), "fake")
    assert turn.prompt_source == "built-in"
    assert len(checks) == len(turn.claims) == 2
