# Project Charter

| Item | Detail |
|---|---|
| Project title | Multi-Agent AI-Powered Business Research & Growth Analysis System |
| Business area | Finance: company research and financial analysis |
| Location | Pune |
| Team | Hariharan Madiajagane (Mentor: Shefali Jain); Pukit Mehta (Mentor: Adriza Paul) |

## Target Users
- Financial analysts
- Business research analysts
- Market research teams
- Business development professionals

## Current Business Problem
Financial filings and company news are scattered across separate sources and formats, which makes company research time-consuming and difficult to reproduce.

## Why the Problem Matters
Timely and consistent understanding of financial performance, growth trends and business developments supports better-informed business decisions. Manual consolidation limits the number of companies that can be analysed and increases the risk of inconsistent or untraceable conclusions.

## Proposed AI Solution
A full-stack application that combines SEC EDGAR financial data, Python-based financial analysis, Statsmodels revenue forecasting and NewsData.io news intelligence. Three LangGraph agents (Financial Analysis and Forecasting, Business News Intelligence, Strategic Research and Decision Support) generate structured, evidence-referenced reports.

## Expected User Outcome
Users select a supported company and receive financial analysis, growth trends, revenue estimates with stated limitations, categorised news, potential risks and opportunities, and a stored research report. Multi-company comparison, change detection between refreshes and downloadable (PDF) reports are planned.

## Project Objectives
1. Collect financial data from SEC EDGAR.
2. Calculate growth rates and financial ratios deterministically.
3. Estimate future revenue trends with a justified time-series model and baseline comparison.
4. Collect and categorise company news from NewsData.io.
5. Detect significant changes between data refreshes.
6. Identify risks and opportunities using transparent rules and AI-assisted interpretation.
7. Generate evidence-backed research reports.

## Project Scope
- Implemented companies: Microsoft and NVIDIA. Apple, Alphabet and Amazon are planned.
- Annual and quarterly financial analysis.
- Basic revenue forecasting with uncertainty intervals where supported.
- News collection, deduplication, categorisation and summarisation.
- Competitor change detection with configurable thresholds.
- Three-agent LangGraph workflow.
- FastAPI backend with SQLite (implemented); React frontend and Azure SQL Database (planned).

## Out-of-Scope Features
- Stock price prediction.
- Stock trading, buy/sell signals and investment recommendations.
- Deep-learning forecasting.
- Unrestricted autonomous AI browsing.
- Real-time market monitoring.
- Paid financial data providers.

## Success Criteria
- Financial data for each supported company is retrieved from SEC EDGAR and stored with source references.
- Financial metrics are calculated in Python and verified by automated tests.
- Forecasts are shown only where sufficient history exists, with model, data period and limitations displayed.
- News items retain original source URLs.
- Reports distinguish verified facts, calculated metrics, model forecasts and AI interpretations.
- Research workflows run through three LangGraph agents with recorded execution status and duration.
- Application runs locally and has a documented Azure deployment path.
