"""The model seam (AGENTS.md): every model call in this project goes through here, and only here.

In-tenant only. ``FoundryProvider`` posts to the firm's Azure AI (Foundry) resource over its OpenAI-compatible
``/chat/completions`` endpoint, signed in with an Entra token (the job's identity in Azure, ``az login``
locally): no API key anywhere. The endpoint host must be on ``APPROVED_MODEL_HOSTS``, a default-deny list
that changes only by commit. The model has no tools; it receives text and must answer with one JSON object
(``response_format`` json_object), which the caller checks against its contract before storing anything.
Nothing from a letter is logged here: only sizes, token counts and the model that answered.

Copied as a pattern from the Tamale repo's ``tamale.llm`` (W-022), not shared as a module (W-002).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .db.connect import TokenError, token_from_az_cli, token_from_container_identity

MODEL_TOKEN_RESOURCE = "https://cognitiveservices.azure.com"
# In-tenant hosts approved to receive letter text. tocqv-research-ai is the firm's own Azure AI Services
# resource on corporate billing, approved for firm research content in the Tamale repo (owner, 2026-08-11).
# Adding a host is a commit, never an environment variable: default deny, no override.
APPROVED_MODEL_HOSTS = ("tocqv-research-ai.cognitiveservices.azure.com",)
TOKEN_LIFETIME = 45 * 60  # seconds; Entra tokens last about an hour
RETRY_STATUSES = (429, 500, 502, 503, 504)
ATTEMPTS = 3


class ModelError(RuntimeError):
    """The endpoint could not be reached or refused the call."""


class ModelReplyError(ModelError):
    """The model answered, but not with usable JSON."""


class HostNotApproved(ModelError):
    """The configured endpoint is not on APPROVED_MODEL_HOSTS."""


class Provider(Protocol):
    """What the extraction code needs from a model: one JSON object per call, and what it cost."""

    model: str
    last_usage: dict | None
    last_model: str

    def complete_json(self, system: str, user: str, *, max_tokens: int = 8000) -> dict: ...


def parse_json_reply(text: str) -> dict:
    """The reply as one JSON object. Code fences are tolerated; anything else is refused."""
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        data = json.loads(s)
    except json.JSONDecodeError as e:
        raise ModelReplyError(f"reply is not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ModelReplyError("reply is not a JSON object")
    return data


def model_token_source() -> Callable[[], str]:
    """A token for the AI resource: the job's identity in Azure, the developer's az login elsewhere."""
    if os.environ.get("IDENTITY_ENDPOINT"):
        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        if not client_id:
            raise TokenError("AZURE_CLIENT_ID not set: the identity's client id must be passed to the job")
        return lambda: token_from_container_identity(client_id, resource=MODEL_TOKEN_RESOURCE)
    return lambda: token_from_az_cli(resource=MODEL_TOKEN_RESOURCE)


@dataclass(frozen=True)
class ModelSettings:
    endpoint: str  # the OpenAI-compatible base, e.g. https://<resource>.cognitiveservices.azure.com/openai/v1
    deployment: str  # the deployment name on that resource
    # Reasoning models think before they answer and bill those tokens against the output budget; extraction
    # is reading, not puzzle-solving, so "low" by default (WHALES_MODEL_REASONING: low, medium, high, none).
    reasoning_effort: str | None = "low"

    @classmethod
    def from_env(cls) -> ModelSettings:
        endpoint = os.environ.get("WHALES_MODEL_ENDPOINT", "").strip()
        deployment = os.environ.get("WHALES_MODEL_DEPLOYMENT", "").strip()
        if not endpoint or not deployment:
            raise ModelError(
                "WHALES_MODEL_ENDPOINT and WHALES_MODEL_DEPLOYMENT must be set (see .env.example)"
            )
        effort = os.environ.get("WHALES_MODEL_REASONING", "low").strip().lower() or "low"
        return cls(endpoint, deployment, None if effort == "none" else effort)


class FoundryProvider:
    """OpenAI-compatible chat completions on the firm's in-tenant endpoint; JSON replies only."""

    def __init__(
        self,
        settings: ModelSettings,
        token_source: Callable[[], str] | None = None,
        *,
        opener: Callable = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: int = 180,
    ):
        parts = urllib.parse.urlsplit(settings.endpoint)
        host = parts.hostname or ""
        if parts.scheme != "https" or host not in APPROVED_MODEL_HOSTS:
            raise HostNotApproved(
                f"{host or settings.endpoint!r} is not an approved in-tenant model host "
                "(whales.llm.APPROVED_MODEL_HOSTS); letter text goes nowhere else"
            )
        self.url = settings.endpoint.rstrip("/") + "/chat/completions"
        self.host = host
        self.model = settings.deployment
        self._token_source = token_source or model_token_source()
        self._opener, self._sleep, self._clock, self._timeout = opener, sleep, clock, timeout
        self._token: str | None = None
        self._token_at = 0.0
        # Newer deployments want max_completion_tokens; an older one answers 400 and we learn max_tokens once.
        self._token_param = "max_completion_tokens"
        # Dropped once if the deployment rejects it (a model without reasoning control answers 400).
        self._reasoning: str | None = settings.reasoning_effort
        self.last_usage: dict | None = None
        self.last_model = ""
        self.totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def _bearer(self, fresh: bool = False) -> str:
        if fresh or self._token is None or self._clock() - self._token_at > TOKEN_LIFETIME:
            self._token = self._token_source()
            self._token_at = self._clock()
        return self._token

    def _post(self, body: dict, *, fresh_token: bool = False) -> tuple[int, dict | str]:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._bearer(fresh_token)}",
            },
        )
        try:
            with self._opener(request, timeout=self._timeout) as r:
                return getattr(r, "status", 200), json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
            return e.code, text
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise ModelError(f"could not reach {self.host}: {e}") from e

    def complete_json(self, system: str, user: str, *, max_tokens: int = 8000) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        fresh_token = False
        token_refreshed = False
        for attempt in range(1, ATTEMPTS + 1):
            body.pop("max_tokens", None)
            body.pop("max_completion_tokens", None)
            body.pop("reasoning_effort", None)
            body[self._token_param] = max_tokens
            if self._reasoning:
                body["reasoning_effort"] = self._reasoning
            status, payload = self._post(body, fresh_token=fresh_token)
            fresh_token = False
            if (
                status == 400
                and self._token_param == "max_completion_tokens"
                and "max_completion_tokens" in str(payload)
            ):
                self._token_param = "max_tokens"
                continue
            if status == 400 and self._reasoning and "reasoning_effort" in str(payload):
                self._reasoning = None  # this deployment takes no reasoning control; learn it once
                continue
            if status == 401 and not token_refreshed:
                fresh_token = token_refreshed = True
                continue
            if status in RETRY_STATUSES and attempt < ATTEMPTS:
                self._sleep(5.0 * attempt)
                continue
            if status != 200 or not isinstance(payload, dict):
                raise ModelError(f"HTTP {status} from {self.host}: {str(payload)[:300]}")
            self.totals["calls"] += 1
            usage = payload.get("usage") or {}
            self.last_usage = {
                "input_tokens": int(usage.get("prompt_tokens") or 0),
                "output_tokens": int(usage.get("completion_tokens") or 0),
            }
            self.totals["input_tokens"] += self.last_usage["input_tokens"]
            self.totals["output_tokens"] += self.last_usage["output_tokens"]
            self.last_model = str(payload.get("model") or "")
            choice = (payload.get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content") or ""
            if not text.strip():
                finish = choice.get("finish_reason")
                if finish == "length":
                    # the reasoning consumed the whole output budget; another identical call would too
                    raise ModelReplyError(
                        f"empty reply from {self.model}: the output budget of {max_tokens} tokens was used "
                        "up before any visible text (finish_reason 'length'); raise max_tokens or lower "
                        "the reasoning effort"
                    )
                if attempt < ATTEMPTS:
                    continue  # an empty reply happens on some deployments; once more, then fail loudly
                raise ModelReplyError(f"empty reply from {self.model} (finish_reason={finish!r})")
            return parse_json_reply(text)
        raise ModelError(f"gave up on {self.host} after {ATTEMPTS} attempts")
