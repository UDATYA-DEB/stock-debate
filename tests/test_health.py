"""Health checks against fake HTTP servers (httpx.MockTransport), no network."""

import httpx

from stockdebate.llm.health import check_gemini, check_openai_compatible, list_models


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def openai_server(models=("qwen3:8b",), require_token=None, generate_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if require_token and request.headers.get("Authorization") != f"Bearer {require_token}":
            return httpx.Response(401)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(generate_status, json={"choices": [{"message": {"content": "OK"}}]})
        return httpx.Response(404)
    return handler


def test_openai_compatible_ok_and_url_normalised():
    r = check_openai_compatible("Bull", "http://localhost:11434/", "qwen3:8b",
                                client=_client(openai_server()))
    assert r.ok, r.detail


def test_placeholder_url_rejected():
    r = check_openai_compatible("Bear", "https://your-tunnel.example.com", "x")
    assert not r.ok and "example" in r.detail


def test_missing_model_lists_available():
    r = check_openai_compatible("Bull", "http://localhost:11434", "qwen3:8b",
                                client=_client(openai_server(models=("llama3:8b",))))
    assert not r.ok
    assert "llama3:8b" in r.detail


def test_token_sent_and_checked():
    server = openai_server(require_token="secret")
    assert check_openai_compatible("Bear", "https://t.dev", "qwen3:8b", token="secret",
                                   client=_client(server)).ok
    bad = check_openai_compatible("Bear", "https://t.dev", "qwen3:8b", token="wrong",
                                  client=_client(server))
    assert not bad.ok and "Authentication" in bad.detail


def test_connection_error_is_explained():
    def refuse(request):
        raise httpx.ConnectError("refused")
    r = check_openai_compatible("Bull", "http://localhost:11434", "m", client=_client(refuse))
    assert not r.ok and "Cannot connect" in r.detail


def test_list_models_sorted_with_token():
    server = openai_server(models=("qwen3:8b", "gemma3:4b"), require_token="secret")
    result = list_models("https://t.dev/v1", token="secret", client=_client(server))
    assert result.error is None
    assert result.models == ["gemma3:4b", "qwen3:8b"]


def test_list_models_empty_server_explained():
    result = list_models("http://localhost:11434", client=_client(openai_server(models=())))
    assert result.models == [] and "no models" in result.error


def test_check_requires_a_selected_model():
    r = check_openai_compatible("Bull", "http://localhost:11434", "", client=_client(openai_server()))
    assert not r.ok and "No model selected" in r.detail


def gemini_server(key="good-key", generate_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-goog-api-key") != key:
            return httpx.Response(400)
        assert "key=" not in str(request.url)  # key must never be in the URL
        if request.url.path == "/v1beta/models":
            return httpx.Response(200, json={"models": [
                {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/text-embedding", "supportedGenerationMethods": ["embedContent"]},
            ]})
        if request.url.path.endswith(":generateContent"):
            return httpx.Response(generate_status, json={"candidates": []})
        return httpx.Response(404)
    return handler


def test_gemini_ok():
    r = check_gemini("good-key", "gemini-2.5-flash", client=_client(gemini_server()))
    assert r.ok, r.detail
    assert r.available_models == ["gemini-2.5-flash"]  # embedding model filtered out


def test_gemini_bad_key():
    r = check_gemini("bad-key", "gemini-2.5-flash", client=_client(gemini_server()))
    assert not r.ok and "rejected" in r.detail


def test_gemini_quota():
    r = check_gemini("good-key", "gemini-2.5-flash", client=_client(gemini_server(generate_status=429)))
    assert not r.ok and "quota" in r.detail


def test_gemini_unknown_model_suggests_options():
    r = check_gemini("good-key", "gemini-0-old", client=_client(gemini_server()))
    assert not r.ok and "gemini-2.5-flash" in r.detail
