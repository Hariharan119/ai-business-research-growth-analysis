# Multi-Agent AI-Powered Business Research & Growth Analysis System

**Domain:** Finance
**Status:** Backend MVP implemented and verified in Google Colab (FastAPI, SQLite, three LangGraph agents). React frontend and Azure deployment are planned.

## Project Overview

An AI-powered financial research and decision-support application that combines SEC EDGAR financial data, historical growth analysis, basic revenue forecasting and NewsData.io business news intelligence. Three specialised LangGraph agents coordinate the analysis and produce evidence-backed research reports.

## Business Problem

Financial and business information is distributed across regulatory filings and news sources. Collecting, normalising and interpreting this information manually is time-consuming and inconsistent. Analysts need a single, traceable view of company performance, growth trends and business developments.

## Proposed Solution

- Collect financial data from SEC EDGAR and news metadata from NewsData.io.
- Perform financial calculations deterministically in Python (Pandas, NumPy).
- Estimate future revenue trends with Statsmodels time-series models compared against a baseline.
- Use LLM-assisted agents for interpretation, news classification and report generation.
- Store data, reports and refresh history in SQLite during development (Azure SQL Database is planned for deployment).

## Key MVP Features

1. Financial data collection and analysis.
2. Historical growth analysis and basic revenue forecasting.
3. Company news intelligence.
4. Competitor change and risk detection.
5. Multi-agent AI research and decision-support reports.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend (planned) | React, TypeScript, Vite, Tailwind CSS, Recharts |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| Multi-agent AI | LangGraph (sequential workflow), Groq-hosted LLM via an OpenAI-compatible API |
| Financial analysis | Pandas, NumPy, Statsmodels |
| Database | SQLite (current); Microsoft Azure SQL Database (planned) |
| DevOps | GitHub (current); Docker, GitHub Actions, Microsoft Azure (planned) |
| Testing | Pytest, React Testing Library |

## Data Sources

- **SEC EDGAR API** (companyfacts and submissions): annual and quarterly financial data.
- **NewsData.io API**: news article metadata, snippets and links.

Supported companies: Microsoft (MSFT) and NVIDIA (NVDA), configured in `backend/app/core/companies.py`. Apple, Alphabet and Amazon are planned.

## Team

| Member | Mentor |
|---|---|
| Hariharan Madiajagane | Shefali Jain |
| Pukit Mehta | Adriza Paul |

Location: Pune

## Planned Architecture

Component, data flow, workflow and sequence diagrams are available in [docs/architecture.md](docs/architecture.md).

## Documentation

- [Problem statement](docs/problem_statement.md)
- [Project charter](docs/project_charter.md)
- [MVP scope](docs/mvp_scope.md)
- [Architecture](docs/architecture.md)
- [Technology stack](docs/technology_stack.md)
- [Team responsibilities](docs/team_responsibilities.md)
- [Azure readiness](docs/azure_readiness.md)
- [Project plan](docs/project_plan.md)

## Setup Instructions

The backend is currently built and verified by running the project notebook in Google Colab (Runtime > Run all) with the `GITHUB_TOKEN`, `GROQ_API_KEY`, `NEWSDATA_API_KEY` and `SEC_USER_AGENT` secrets. Local setup instructions will be added when the project moves to VS Code.

## Disclaimer

Forecasts are statistical estimates and are not guaranteed outcomes. The system does not predict stock prices, execute trades or provide investment recommendations.
