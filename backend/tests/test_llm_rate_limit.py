# Client-side tokens-per-minute limiter, tested with a fake clock (no network).

import asyncio

from app.services import llm_client


def use_fake_clock(monkeypatch):
    clock = {"now": 1000.0}
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(llm_client, "_monotonic", lambda: clock["now"])
    monkeypatch.setattr(llm_client, "_sleep", fake_sleep)
    llm_client._token_log.clear()
    return clock, slept


def test_estimate_counts_prompt_and_reserved_completion():
    body = {"messages": [{"role": "user", "content": "x" * 300}], "max_completion_tokens": 100}
    assert llm_client._estimate_request_tokens(body) == 200
    assert llm_client._estimate_request_tokens(None) == 0


def test_waits_until_the_one_minute_window_has_room(monkeypatch):
    clock, slept = use_fake_clock(monkeypatch)

    asyncio.run(llm_client._wait_for_token_budget(60, 100))
    asyncio.run(llm_client._wait_for_token_budget(30, 100))
    assert slept == []  # 90 of 100 used, both fit

    asyncio.run(llm_client._wait_for_token_budget(30, 100))
    assert len(slept) == 1 and 60.0 <= slept[0] <= 61.0  # waited for the first entry to expire
    llm_client._token_log.clear()


def test_rejected_requests_free_their_budget(monkeypatch):
    clock, slept = use_fake_clock(monkeypatch)

    entry = asyncio.run(llm_client._wait_for_token_budget(90, 100))
    entry[1] = 0  # what _send does after a 429
    asyncio.run(llm_client._wait_for_token_budget(90, 100))
    assert slept == []
    llm_client._token_log.clear()


def test_limit_zero_disables_the_limiter(monkeypatch):
    clock, slept = use_fake_clock(monkeypatch)
    assert asyncio.run(llm_client._wait_for_token_budget(10_000, 0)) is None
    assert slept == []
