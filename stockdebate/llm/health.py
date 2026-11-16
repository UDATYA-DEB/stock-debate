"""Health checks for the three model endpoints.

Each check: connect, confirm the configured model exists, then send a tiny
prompt to prove the model actually answers. Messages are written for a person
fixing their setup, not for a log file.

- Bull and bear: any OpenAI-compatible server (Ollama and vLLM both are).
- Judge: Google Gemini API.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from pydantic import BaseModel

from stockdebate.llm.config import RuntimeConfig

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
PING = "Reply with the single word OK."
# First call can be slow: the server may need to load the model into memory.
GENERATE_TIMEOUT = 180.0
LIST_TIMEOUT = 15.0


class HealthResult(BaseModel):
    name: str
    ok: bool
    detail: str
    latency_ms: int | None = None
    available_models: list[str] = []


def _openai_base(url: str) -> str:
    url = url.strip().rstrip("/")
    return url if url.endswith("/v1") else f"{url}/v1"


def _looks_like_placeholder(url: str) -> bool:
    return "example" in url.lower()


class ModelList(BaseModel):
    models: list[str] = []
    error: str | None = None


def list_models(url: str, token: str | None = None,
                client: httpx.Client | None = None) -> ModelList:
    """Models served by an OpenAI-compatible endpoint (GET /v1/models)."""
    if not url.strip():
        return ModelList(error="No URL entered.")
    if _looks_like_placeholder(url):
        return ModelList(error="This is the example URL. Replace it with your real endpoint.")
    base = _openai_base(url)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    own_client = client is None
    client = client or httpx.Client()
    try:
        try:
            resp = client.get(f"{base}/models", headers=headers, timeout=LIST_TIMEOUT)
        except httpx.ConnectError:
            return ModelList(error=f"Cannot connect to {url}. Is the server running (or the tunnel up)?")
        except httpx.TimeoutException:
            return ModelList(error=f"{url} did not respond in time.")
        if resp.status_code in (401, 403):
            return ModelList(error="Authentication failed. Check the token.")
        if resp.status_code != 200:
            return ModelList(error=f"Unexpected response from {base}/models (HTTP {resp.status_code}). "
                                   "Is this an Ollama or OpenAI-compatible server?")
        try:
            models = sorted(m["id"] for m in resp.json().get("data", []) if m.get("id"))
        except ValueError:
            return ModelList(error=f"{base}/models did not return JSON.")
        if not models:
            return ModelList(error="The server is running but has no models. "
                                   "Pull one first (e.g. `ollama pull qwen3:8b`).")
        return ModelList(models=models)
    finally:
        if own_client:
            client.close()


def check_openai_compatible(name: str, url: str, model: str, token: str | None = None,
                            client: httpx.Client | None = None) -> HealthResult:
    if not model.strip():
        return HealthResult(name=name, ok=False, detail="No model selected.")
    own_client = client is None
    client = client or httpx.Client()
    try:
        listed = list_models(url, token, client)
        if listed.error:
            return HealthResult(name=name, ok=False, detail=listed.error)
        models = listed.models
        base = _openai_base(url)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if model not in models:
            listed = ", ".join(models) if models else "none"
            return HealthResult(name=name, ok=False, available_models=models,
                                detail=f"Model '{model}' is not available on this server. "
                                       f"Available: {listed}.")

        start = time.monotonic()
        try:
            resp = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": PING}],
                      "max_tokens": 16},
                timeout=GENERATE_TIMEOUT,
            )
        except httpx.TimeoutException:
            return HealthResult(name=name, ok=False, available_models=models,
                                detail=f"'{model}' did not answer within {GENERATE_TIMEOUT:.0f}s.")
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code != 200 or not resp.json().get("choices"):
            return HealthResult(name=name, ok=False, available_models=models, latency_ms=latency,
                                detail=f"'{model}' failed to answer (HTTP {resp.status_code}).")
        return HealthResult(name=name, ok=True, available_models=models, latency_ms=latency,
                            detail=f"'{model}' answered in {latency / 1000:.1f}s.")
    finally:
        if own_client:
            client.close()


def check_gemini(api_key: str, model: str, client: httpx.Client | None = None) -> HealthResult:
    name = "Judge (Gemini)"
    if not api_key.strip():
        return HealthResult(name=name, ok=False, detail="No API key entered.")
    if api_key.strip().endswith("..."):
        return HealthResult(name=name, ok=False, detail="This is the example key. Enter your real key.")
    headers = {"x-goog-api-key": api_key.strip()}  # header, so the key never appears in URLs
    own_client = client is None
    client = client or httpx.Client()
    try:
        try:
            resp = client.get(f"{GEMINI_BASE}/models", headers=headers,
                              params={"pageSize": 1000}, timeout=LIST_TIMEOUT)
        except (httpx.ConnectError, httpx.TimeoutException):
            return HealthResult(name=name, ok=False,
                                detail="Cannot reach the Gemini API. Check your internet connection.")
        if resp.status_code in (400, 401, 403):
            return HealthResult(name=name, ok=False, detail="The API key was rejected.")
        if resp.status_code != 200:
            return HealthResult(name=name, ok=False,
                                detail=f"Unexpected response from Gemini (HTTP {resp.status_code}).")
        models = sorted(m.get("name", "").removeprefix("models/")
                        for m in resp.json().get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", []))
        if model not in models:
            suggestions = [m for m in models if "flash" in m][:8] or models[:8]
            return HealthResult(name=name, ok=False, available_models=models,
                                detail=f"Model '{model}' is not available for this key. "
                                       f"Some options: {', '.join(suggestions)}.")

        start = time.monotonic()
        resp = client.post(
            f"{GEMINI_BASE}/models/{model}:generateContent",
            headers=headers,
            json={"contents": [{"parts": [{"text": PING}]}],
                  "generationConfig": {"maxOutputTokens": 16}},
            timeout=60.0,
        )
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code == 429:
            return HealthResult(name=name, ok=False, available_models=models, latency_ms=latency,
                                detail="Rate limit or free quota exceeded. Try again later.")
        if resp.status_code != 200:
            return HealthResult(name=name, ok=False, available_models=models, latency_ms=latency,
                                detail=f"'{model}' failed to answer (HTTP {resp.status_code}).")
        return HealthResult(name=name, ok=True, available_models=models, latency_ms=latency,
                            detail=f"'{model}' answered in {latency / 1000:.1f}s.")
    finally:
        if own_client:
            client.close()


LANGFUSE_NAME = "Observability (Langfuse)"


def check_langfuse(public_key: str | None, secret_key: str | None, host: str | None,
                   obs_factory=None) -> HealthResult:
    """Langfuse is optional: blank keys mean tracing off and built-in prompts."""
    from stockdebate.obs.tracing import Observability

    if not public_key and not secret_key:
        return HealthResult(name=LANGFUSE_NAME, ok=True,
                            detail="Not configured: tracing is off and built-in prompts are used.")
    if not (public_key and secret_key):
        return HealthResult(name=LANGFUSE_NAME, ok=False, detail="Enter both the public and the secret key.")
    if public_key.endswith("...") or secret_key.endswith("..."):
        return HealthResult(name=LANGFUSE_NAME, ok=False, detail="These are the example keys. Enter your real keys.")
    obs = (obs_factory or Observability.from_keys)(public_key, secret_key, host)
    try:
        if not obs.client.auth_check():
            return HealthResult(name=LANGFUSE_NAME, ok=False,
                                detail="Keys rejected. Check them, and that the host matches your "
                                       "project's region.")
    except Exception as exc:
        return HealthResult(name=LANGFUSE_NAME, ok=False, detail=f"Cannot reach Langfuse at {host}: {exc}")
    missing = obs.missing_prompts()
    if missing:
        return HealthResult(name=LANGFUSE_NAME, ok=False, available_models=missing,
                            detail=f"Connected, but these prompts don't exist in Langfuse yet: "
                                   f"{', '.join(missing)}. Use 'Push default prompts'.")
    return HealthResult(name=LANGFUSE_NAME, ok=True, detail="Connected; prompts found.")


def check_all(config: RuntimeConfig) -> list[HealthResult]:
    """Run all checks in parallel; results in order judge, bull, bear, Langfuse."""
    token = config.bear_token.get_secret_value() if config.bear_token else None
    with ThreadPoolExecutor(max_workers=4) as pool:
        judge = pool.submit(check_gemini, config.gemini_api_key.get_secret_value(), config.judge_model)
        bull = pool.submit(check_openai_compatible, "Bull agent (local)", config.bull_url,
                           config.bull_model)
        bear = pool.submit(check_openai_compatible, "Bear agent (Kaggle)", config.bear_url,
                           config.bear_model, token)
        langfuse = pool.submit(check_langfuse, config.langfuse_public_key, config.langfuse_secret,
                               config.langfuse_host)
        return [judge.result(), bull.result(), bear.result(), langfuse.result()]
