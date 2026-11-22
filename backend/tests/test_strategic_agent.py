# Strategic Agent evidence rules, tested with a fake LLM client (no Groq calls).

import asyncio

from app.agents import strategic_agent
from app.schemas.agent_schemas import StrategicAgentOutput

TRUSTED_URL = "https://www.sec.gov/Archives/edgar/data/trusted-filing"


class FakeLlmClient:
    def __init__(self, output):
        self.output = output

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def complete_json(self, **kwargs):
        return self.output


def make_state():
    return {
        "ticker": sorted(strategic_agent.SUPPORTED_TICKERS)[0],
        "financial_agent_output": {
            "overall_assessment": "Stable growth.",
            "evidence": [{"source_type": "SEC", "source_url": TRUSTED_URL, "note": "Revenue"}],
        },
        "news_agent_output": {"overall_assessment": "Limited coverage."},
    }


def priority(name, evidence):
    return {
        "priority": name,
        "rationale": "Rationale.",
        "suggested_action": "Action.",
        "supporting_evidence": evidence,
    }


def test_priorities_without_traceable_evidence_are_removed_and_reported(monkeypatch):
    output = StrategicAgentOutput(
        executive_summary="Summary.",
        strategic_priorities=[
            priority("Backed", [{"source_type": "SEC", "source_url": TRUSTED_URL, "note": "n"}]),
            priority("Invented URL", [{"source_type": "NEWS", "source_url": "https://invented.example/x", "note": "n"}]),
            priority("No evidence", []),
        ],
        confidence="medium",
    )
    monkeypatch.setattr(strategic_agent, "get_settings", lambda: None)
    monkeypatch.setattr(strategic_agent, "LlmClient", lambda settings: FakeLlmClient(output))

    result = asyncio.run(strategic_agent.run_strategic_agent(make_state()))

    assert result["strategic_agent_error"] == ""
    report = result["strategic_agent_output"]
    assert [item["priority"] for item in report["strategic_priorities"]] == ["Backed"]
    assert report["strategic_priorities"][0]["supporting_evidence"][0]["source_url"] == TRUSTED_URL
    assert any(
        "Invented URL" in limitation and "No evidence" in limitation
        for limitation in report["limitations"]
    )


def test_unsupported_ticker_is_rejected_without_llm_call(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr(strategic_agent, "LlmClient", fail)
    state = make_state()
    state["ticker"] = "ZZZZ"

    result = asyncio.run(strategic_agent.run_strategic_agent(state))

    assert "Unsupported ticker" in result["strategic_agent_error"]
