"""Language model client for OpenAI-compatible chat completion APIs with validated JSON output."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError, LlmResponseError, LlmUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 30.0


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

        attempt = 1
        while True:
            response: Optional[httpx.Response] = None
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
                if status == 400:
                    raise LlmResponseError(f"LLM request rejected (HTTP 400): {_error_message(response)}")
                if status < 400:
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

            if attempt >= self._settings.llm_max_attempts:
                raise LlmUnavailableError(error)
            delay = _retry_after(response)
            if delay is None:
                delay = self._retry_base_delay * (2 ** (attempt - 1))
            logger.warning("llm_retry", extra={"attempt": attempt, "delay_seconds": delay, "error": error})
            await asyncio.sleep(delay)
            attempt += 1
