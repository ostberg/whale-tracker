"""The model seam (W-052) against a fake endpoint: approved hosts, the request, retries, replies."""

import io
import json
import urllib.error

import pytest

from whales import llm

ENDPOINT = "https://tocqv-research-ai.cognitiveservices.azure.com/openai/v1"
SETTINGS = llm.ModelSettings(ENDPOINT, "gpt-test")


class _Response:
    def __init__(self, payload):
        self.status = 200
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _reply(content, model="gpt-test-2026", usage=(10, 5), finish="stop"):
    return {
        "model": model,
        "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
    }


def fake_endpoint(script):
    """An opener answering with ``script`` items in order: a dict (200 + JSON) or (status, text)."""
    seen = []

    def opener(request, timeout):
        seen.append(request)
        item = script.pop(0)
        if isinstance(item, tuple):
            status, text = item
            raise urllib.error.HTTPError(request.full_url, status, "x", {}, io.BytesIO(text.encode()))
        return _Response(item)

    return opener, seen


def provider(script, tokens=None):
    opener, seen = fake_endpoint(script)
    tokens = tokens or iter(["tok1", "tok2", "tok3"])
    p = llm.FoundryProvider(
        SETTINGS, lambda: next(tokens), opener=opener, sleep=lambda s: None, clock=lambda: 0.0
    )
    return p, seen


def test_request_shape_and_reply():
    p, seen = provider([_reply('{"predictions": []}')])
    assert p.complete_json("sys", "user", max_tokens=123) == {"predictions": []}
    req = seen[0]
    assert req.full_url == ENDPOINT + "/chat/completions"
    assert req.get_header("Authorization") == "Bearer tok1"
    body = json.loads(req.data)
    assert body["model"] == "gpt-test" and body["response_format"] == {"type": "json_object"}
    assert body["max_completion_tokens"] == 123 and "max_tokens" not in body
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert p.last_model == "gpt-test-2026" and p.last_usage == {"input_tokens": 10, "output_tokens": 5}
    assert p.totals == {"calls": 1, "input_tokens": 10, "output_tokens": 5}


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.openai.com/v1",
        "https://evil.example/openai/v1",
        "http://tocqv-research-ai.cognitiveservices.azure.com/openai/v1",
        "https://tocqv-research-ai.cognitiveservices.azure.com.evil.example/openai/v1",
    ],
)
def test_only_approved_https_hosts(endpoint):
    with pytest.raises(llm.HostNotApproved):
        llm.FoundryProvider(llm.ModelSettings(endpoint, "x"), lambda: "t", opener=None)


def test_older_deployment_learns_max_tokens_once():
    p, seen = provider([(400, "Unsupported parameter: 'max_completion_tokens'"), _reply("{}"), _reply("{}")])
    p.complete_json("s", "u", max_tokens=50)
    p.complete_json("s", "u", max_tokens=50)
    bodies = [json.loads(r.data) for r in seen]
    assert "max_completion_tokens" in bodies[0]
    assert bodies[1]["max_tokens"] == 50 and bodies[2]["max_tokens"] == 50 and len(seen) == 3


def test_expired_token_is_refreshed_once():
    p, seen = provider([(401, "token expired"), _reply("{}")])
    p.complete_json("s", "u")
    assert [r.get_header("Authorization") for r in seen] == ["Bearer tok1", "Bearer tok2"]


def test_token_is_cached_within_its_lifetime():
    p, seen = provider([_reply("{}"), _reply("{}")])
    p.complete_json("s", "u")
    p.complete_json("s", "u")
    assert [r.get_header("Authorization") for r in seen] == ["Bearer tok1", "Bearer tok1"]


def test_throttling_is_retried_then_fails_loudly():
    p, _ = provider([(429, "slow down"), (503, "busy"), (429, "slow down")])
    with pytest.raises(llm.ModelError, match="HTTP 429"):
        p.complete_json("s", "u")


def test_other_http_errors_fail_at_once():
    p, seen = provider([(403, "forbidden")])
    with pytest.raises(llm.ModelError, match="HTTP 403"):
        p.complete_json("s", "u")
    assert len(seen) == 1


def test_empty_reply_is_retried_then_refused():
    p, seen = provider([_reply(""), _reply("  "), _reply("")])
    with pytest.raises(llm.ModelReplyError, match="empty reply"):
        p.complete_json("s", "u")
    assert len(seen) == 3


def test_reasoning_effort_is_sent_low_and_dropped_if_refused():
    p, seen = provider([_reply("{}")])
    p.complete_json("s", "u")
    assert json.loads(seen[0].data)["reasoning_effort"] == "low"
    refused = (400, "Unrecognized request argument supplied: reasoning_effort")
    p, seen = provider([refused, _reply("{}"), _reply("{}")])
    p.complete_json("s", "u")
    p.complete_json("s", "u")
    assert "reasoning_effort" not in json.loads(seen[1].data) and len(seen) == 3
    opener, seen = fake_endpoint([_reply("{}")])
    settings = llm.ModelSettings(ENDPOINT, "x", reasoning_effort=None)
    quiet = llm.FoundryProvider(settings, lambda: "t", opener=opener)
    quiet.complete_json("s", "u")
    assert "reasoning_effort" not in json.loads(seen[0].data)


def test_budget_exhausted_by_reasoning_fails_at_once_with_advice():
    p, seen = provider([_reply("", finish="length")])
    with pytest.raises(llm.ModelReplyError, match="output budget of 8000 tokens"):
        p.complete_json("s", "u")
    assert len(seen) == 1  # no retry: the same call would exhaust the budget again


def test_code_fences_are_tolerated_but_non_json_is_not():
    assert llm.parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(llm.ModelReplyError, match="not JSON"):
        llm.parse_json_reply("Sure! Here is the JSON: {")
    with pytest.raises(llm.ModelReplyError, match="not a JSON object"):
        llm.parse_json_reply("[1, 2]")


def test_settings_need_both_variables(monkeypatch):
    monkeypatch.delenv("WHALES_MODEL_ENDPOINT", raising=False)
    monkeypatch.setenv("WHALES_MODEL_DEPLOYMENT", "x")
    with pytest.raises(llm.ModelError, match="WHALES_MODEL_ENDPOINT"):
        llm.ModelSettings.from_env()
    monkeypatch.setenv("WHALES_MODEL_ENDPOINT", ENDPOINT)
    assert llm.ModelSettings.from_env() == llm.ModelSettings(ENDPOINT, "x")


def test_token_source_follows_the_environment(monkeypatch):
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://169.254.169.254/x")
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    with pytest.raises(llm.TokenError, match="AZURE_CLIENT_ID"):
        llm.model_token_source()
    monkeypatch.delenv("IDENTITY_ENDPOINT")
    assert callable(llm.model_token_source())
