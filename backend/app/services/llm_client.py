"""Language model client for OpenAI-compatible chat completion APIs with validated JSON output."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError, LlmResponseError, LlmUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 400 is retried only for invalid generated JSON (see _is_json_generation_error);
# every other 400 is raised immediately in _send.
RETRYABLE_STATUS_CODES = {400, 429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 30.0

# Client-side tokens-per-minute limiter. The provider rejects a request when the
# tokens of the last 60 seconds plus the new request (prompt + reserved
# completion) exceed its per-minute limit, so wait for room instead of failing.
TOKEN_WINDOW_SECONDS = 60.0
_token_log: deque = deque()  # entries are [timestamp, tokens]
_monotonic = time.monotonic
_sleep = asyncio.sleep


def _estimate_request_tokens(body: Optional[dict]) -> int:
    """Conservative estimate: about 3 characters per prompt token plus the reserved completion."""
    if not body or "messages" not in body:
        return 0
    prompt_chars = sum(len(str(message.get("content") or "")) for message in body["messages"])
    reserved = int(body.get("max_completion_tokens") or body.get("max_tokens") or 1024)
    return prompt_chars // 3 + reserved


async def _wait_for_token_budget(tokens: int, limit: int) -> Optional[list]:
    """Wait until `tokens` fit into the rolling one-minute window, then record them."""
    if tokens <= 0 or limit <= 0:
        return None
    while True:
        now = _monotonic()
        while _token_log and now - _token_log[0][0] >= TOKEN_WINDOW_SECONDS:
            _token_log.popleft()
        used = sum(entry[1] for entry in _token_log)
        if not _token_log or used + tokens <= limit:
            entry = [now, tokens]
            _token_log.append(entry)
            return entry
        wait = TOKEN_WINDOW_SECONDS - (now - _token_log[0][0]) + 0.5
        logger.info("llm_rate_limit_wait", extra={"seconds": round(wait, 1), "tokens": tokens, "used": used})
        await _sleep(wait)


def _record_actual_usage(entry: Optional[list], response: httpx.Response) -> None:
    """Replace the estimate with the provider-reported token usage when available."""
    if entry is None:
        return
    try:
        total = int((response.json().get("usage") or {}).get("total_tokens") or 0)
    except (ValueError, AttributeError, TypeError):
        return
    if total > 0:
        entry[1] = total


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.total_tokens += int(usage.get("total_tokens") or 0)


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("response contains no JSON object")
    return text[start : end + 1]


def _error_message(response: httpx.Response) -> str:
    try:
        error = response.json().get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:300]
    except (ValueError, AttributeError):
        pass
    return response.text[:300]


def _is_json_generation_error(response: httpx.Response) -> bool:
    """The provider rejects json_object output that is not valid JSON; regenerating usually succeeds."""
    message = _error_message(response).lower()
    return (
        "failed to validate json" in message
        or "failed to generate json" in message
        or "json_validate_failed" in response.text
    )


def _retry_after(response: Optional[httpx.Response]) -> Optional[float]:
    if response is None:
        return None
    try:
        return min(float(response.headers.get("retry-after", "")), MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        return None


class LlmClient:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        retry_base_delay: float = 2.0,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = http_client
        self._owns_client = http_client is None
        self._retry_base_delay = retry_base_delay

    async def __aenter__(self) -> "LlmClient":
        return self

    async def __aexit__(self, *_exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds)
        return self._client

    async def list_models(self) -> list[str]:
        response = await self._send("GET", "/models")
        data = response.json().get("data", [])
        return sorted(item["id"] for item in data if isinstance(item, dict) and "id" in item)

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        usage: Optional[TokenUsage] = None,
        max_completion_tokens: Optional[int] = None,
    ) -> T:
        """Request a JSON object that conforms to the schema; one repair attempt is made on invalid output."""
        instructions = (
            f"{system}\n\nRespond with one JSON object only, without markdown. "
            f"The object must conform to this JSON schema:\n{json.dumps(schema.model_json_schema())}"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user},
        ]
        last_error: Optional[Exception] = None
        for _attempt in range(2):
            text = await self._chat(
                messages, usage, max_completion_tokens
            )
            try:
                return schema.model_validate_json(_extract_json(text))
            except (ValidationError, ValueError) as exc:
                last_error = exc
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"The JSON was invalid: {str(exc)[:500]}. Return corrected JSON only."},
                ]
        raise LlmResponseError(f"LLM output failed validation: {str(last_error)[:300]}")

    async def _chat(
        self,
        messages: list[dict[str, str]],
        usage: Optional[TokenUsage],
        max_completion_tokens: Optional[int] = None,
    ) -> str:
        try:
            model = self._settings.require_llm_model()
        except ConfigurationError as exc:
            raise LlmUnavailableError(str(exc)) from exc
        body = {
            "model": model,
            "messages": messages,
            "temperature": self._settings.llm_temperature,
            "response_format": {"type": "json_object"},
        }
        if max_completion_tokens is not None:
            body["max_completion_tokens"] = max_completion_tokens

        response = await self._send("POST", "/chat/completions", body)
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LlmResponseError("LLM returned an unexpected response structure") from exc
        if usage is not None:
            usage.add(payload.get("usage"))
        return str(content or "")

    async def _send(self, method: str, path: str, body: Optional[dict] = None) -> httpx.Response:
        try:
            key = self._settings.require_llm_key()
        except ConfigurationError as exc:
            raise LlmUnavailableError(str(exc)) from exc
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        url = self._settings.llm_base_url.rstrip("/") + path
        client = self._ensure_client()

        estimated_tokens = _estimate_request_tokens(body)
        attempt = 1
        while True:
            response: Optional[httpx.Response] = None
            entry = await _wait_for_token_budget(estimated_tokens, self._settings.llm_tokens_per_minute)
            try:
                response = await client.request(method, url, headers=headers, json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                error = f"LLM request failed: {type(exc).__name__}"
            else:
                status = response.status_code
                if status in (401, 403):
                    raise LlmUnavailableError(f"LLM provider rejected the credentials (HTTP {status}).")
                if status == 404:
                    raise LlmUnavailableError("LLM model or endpoint not found (HTTP 404). Check LLM_MODEL and LLM_BASE_URL.")
                if status == 400 and not _is_json_generation_error(response):
                    raise LlmResponseError(f"LLM request rejected (HTTP 400): {_error_message(response)}")
                if status < 400:
                    _record_actual_usage(entry, response)
                    return response
                if status == 413:
                    raise LlmUnavailableError(
                        f"LLM provider returned HTTP 413: {_error_message(response)}"
                    )
                if status not in RETRYABLE_STATUS_CODES:
                    raise LlmUnavailableError(
                        f"LLM provider returned HTTP {status}: {_error_message(response)}"
                    )
                error = (
                    f"LLM provider returned HTTP {status}: "
                    f"{_error_message(response)}"
                )

            if entry is not None:
                entry[1] = 0  # rejected or failed requests do not use the provider's quota
            if attempt >= self._settings.llm_max_attempts:
                if response is not None and response.status_code == 400:
                    raise LlmResponseError(error)  # invalid JSON on every attempt
                raise LlmUnavailableError(error)
            delay = _retry_after(response)
            if delay is None:
                delay = self._retry_base_delay * (2 ** (attempt - 1))
            logger.warning("llm_retry", extra={"attempt": attempt, "delay_seconds": delay, "error": error})
            await asyncio.sleep(delay)
            attempt += 1
