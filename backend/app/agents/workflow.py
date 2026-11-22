import asyncio
import logging
from typing import Any

from langgraph.graph import StateGraph, START, END

from app.agents.state import ResearchState
from app.agents.financial_agent import run_financial_agent
from app.agents.news_agent import run_news_agent
from app.agents.strategic_agent import run_strategic_agent

logger = logging.getLogger(__name__)


async def financial_node(state: ResearchState) -> dict[str, Any]:
    return await run_financial_agent(state)


async def news_node(state: ResearchState) -> dict[str, Any]:
    logger.info("Waiting 65 seconds before News Agent request")
    await asyncio.sleep(65)
    return await run_news_agent(state)


async def strategic_node(state: ResearchState) -> dict[str, Any]:
    if state.get("financial_agent_error"):
        return {
            "strategic_agent_error":
                "Financial Agent failed: "
                + state["financial_agent_error"]
        }

    if state.get("news_agent_error"):
        return {
            "strategic_agent_error":
                "News Agent failed: "
                + state["news_agent_error"]
        }

    logger.info("Waiting 65 seconds before Strategic Agent request")
    await asyncio.sleep(65)
    return await run_strategic_agent(state)


def finalize_node(state: ResearchState) -> dict[str, Any]:
    errors = [
        state.get("financial_agent_error"),
        state.get("news_agent_error"),
        state.get("strategic_agent_error"),
    ]

    if not any(errors):
        status = "completed"
    elif any([
        state.get("financial_agent_output"),
        state.get("news_agent_output"),
        state.get("strategic_agent_output"),
    ]):
        status = "partial_failure"
    else:
        status = "failed"

    return {"workflow_status": status}


def build_research_workflow():
    graph = StateGraph(ResearchState)

    graph.add_node("financial_agent", financial_node)
    graph.add_node("news_agent", news_node)
    graph.add_node("strategic_agent", strategic_node)
    graph.add_node("finalize", finalize_node)

    # Sequential execution avoids simultaneous LLM requests.
    graph.add_edge(START, "financial_agent")
    graph.add_edge("financial_agent", "news_agent")
    graph.add_edge("news_agent", "strategic_agent")
    graph.add_edge("strategic_agent", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


research_workflow = build_research_workflow()
