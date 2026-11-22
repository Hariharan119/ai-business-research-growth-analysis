# LLM client handling of provider-rejected JSON, tested with a mock HTTP transport.

import asyncio

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import LlmResponseError
from app.services.llm_client import LlmClient

INVALID_JSON = {
    "error": {
        "message": "Failed to validate JSON. Please adjust your prompt.",
        "type": "invalid_request_error",
        "code": "json_validate_failed",
    }
}
VALID = {"choices": [{"message": {"content": '{"status": "ok"}'}}], "usage": {"total_tokens": 12}}


class Ping(BaseModel):
    status: str


def make_client(responses, calls):
    def handler(request):
        calls.append(request)
        status, body = responses[min(len(calls), len(responses)) - 1]
        return httpx.Response(status, json=body)

    settings = Settings(
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_attempts=3,
        llm_tokens_per_minute=0,
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LlmClient(settings, http_client=http_client, retry_base_delay=0)


def run(client):
    async def go():
        try:
            return await client.complete_json(system="Return JSON.", user="Status?", schema=Ping)
        finally:
            await client._client.aclose()
    return asyncio.run(go())


def test_invalid_generated_json_is_regenerated():
    calls = []
    result = run(make_client([(400, INVALID_JSON), (200, VALID)], calls))
    assert result.status == "ok"
    assert len(calls) == 2


def test_other_bad_requests_fail_immediately():
    calls = []
    bad_request = {"error": {"message": "model does not support this parameter"}}
    with pytest.raises(LlmResponseError):
        run(make_client([(400, bad_request)], calls))
    assert len(calls) == 1


def test_repeated_invalid_json_raises_response_error():
    calls = []
    with pytest.raises(LlmResponseError):
        run(make_client([(400, INVALID_JSON)], calls))
    assert len(calls) == 3
