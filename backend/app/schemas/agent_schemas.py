
"""Validated output schemas for the multi-agent research system."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictAgentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceReference(StrictAgentSchema):
    source_type: Literal["SEC", "NEWS", "FORECAST"]
    source_url: str
    note: str = Field(min_length=1, max_length=500)
    article_id: int | None = None
    metric_name: str | None = None
    period_end: str | None = None


class MetricInsight(StrictAgentSchema):
    metric_name: str
    observation: str
    interpretation: str
    evidence: list[EvidenceReference] = Field(default_factory=list)


class FinancialAgentOutput(StrictAgentSchema):
    overall_assessment: str
    performance_highlights: list[str] = Field(default_factory=list)
    financial_concerns: list[str] = Field(default_factory=list)
    metric_insights: list[MetricInsight] = Field(default_factory=list)
    forecast_interpretation: str
    forecast_caveats: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]


class NewsSignal(StrictAgentSchema):
    headline: str
    category: str
    explanation: str
    evidence: EvidenceReference


class NewsAgentOutput(StrictAgentSchema):
    overall_assessment: str
    important_topics: list[str] = Field(default_factory=list)
    risk_signals: list[NewsSignal] = Field(default_factory=list)
    opportunities: list[NewsSignal] = Field(default_factory=list)
    competitor_activity: list[str] = Field(default_factory=list)
    source_limitations: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]


class StrategicPriority(StrictAgentSchema):
    priority: str
    rationale: str
    suggested_action: str
    supporting_evidence: list[EvidenceReference] = Field(default_factory=list)


class StrategicAgentOutput(StrictAgentSchema):
    executive_summary: str
    strategic_priorities: list[StrategicPriority] = Field(default_factory=list)
    key_strengths: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    growth_opportunities: list[str] = Field(default_factory=list)
    items_to_monitor: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    limitations: list[str] = Field(default_factory=list)
