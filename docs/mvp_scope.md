# MVP Scope

## Project Type
AI-powered financial research, analytics and decision-support application with a multi-agent workflow.

## Input, Processing, Output

| Stage | Description |
|---|---|
| Input | Selected company or companies; financial reporting period; research request. |
| Processing | SEC EDGAR data retrieval; GDELT news retrieval; financial calculations; historical growth analysis; basic revenue forecasting; change, risk and opportunity identification; coordination of specialised AI agents. |
| Output | Financial analysis; growth trends; estimated revenue forecasts; news intelligence; potential risks and opportunities; evidence-backed research report. |

## MVP Features

1. **Financial Data Collection and Analysis.** SEC EDGAR retrieval, normalisation, storage, growth rates, margins and ratios.
2. **Historical Growth Analysis and Basic Revenue Forecasting.** Baseline and Statsmodels model, backtesting, uncertainty intervals, limitation statements.
3. **Company News Intelligence.** GDELT retrieval, deduplication, categorisation, tone, summaries with source URLs.
4. **Competitor Change and Risk Detection.** Threshold-based change detection, rule-based financial risk and opportunity signals.
5. **Multi-Agent AI Research and Decision-Support Reports.** Three LangGraph agents producing a stored, evidence-referenced report.

## Initial Companies
Microsoft (CIK 0000789019), Apple (CIK 0000320193), Alphabet (CIK 0001652044), Amazon (CIK 0001018724), NVIDIA (CIK 0001045810).

## Postponed Features
- Stock price prediction.
- Stock trading and investment recommendations.
- Complex deep-learning forecasting.
- Unrestricted autonomous AI browsing.
- Real-time stock market monitoring.
- Integration with paid financial data providers.

## Constraints
Forecasts are estimates and not investment advice. Financial ratios are computed deterministically in Python and not by an LLM. GDELT provides article metadata and links, not guaranteed full article text.
