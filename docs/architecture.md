# Architecture

## 1. Component Architecture

```mermaid
flowchart LR
    U["User"] --> FE["React Frontend"]
    FE -->|"REST requests"| API["FastAPI Backend"]
    API --> AUTH["Authentication and Request Validation"]
    AUTH --> DP["Data Processing and Normalisation Service"]
    SEC["SEC EDGAR API"] --> DP
    GD["GDELT DOC API"] --> DP
    DP --> DB[("Azure SQL Database")]
    DB --> FIN["Financial Analysis Service"]
    FIN --> FC["Growth Forecasting Service"]
    AUTH --> LG["LangGraph Orchestration"]
    LG --> A1["Financial Analysis and Forecasting Agent"]
    LG --> A2["Business News Intelligence Agent"]
    FIN --> A1
    FC --> A1
    DB --> A2
    A1 --> A3["Strategic Research and Decision Support Agent"]
    A2 --> A3
    A1 -.-> LLM["Configurable LLM API"]
    A2 -.-> LLM
    A3 -.-> LLM
    A3 --> RPT["Research Report Generation"]
    RPT --> DB
    RPT --> API
    API -->|"Results returned to React"| FE
```

## 2. Data Flow

```mermaid
flowchart TD
    S1["1. User selects a company"] --> S2["2. React sends request to FastAPI"]
    S2 --> S3["3. FastAPI validates the request"]
    S3 --> S4["4. Backend retrieves SEC financial data and GDELT news"]
    S4 --> S5["5. Data is cleaned and normalised"]
    S5 --> S6[("6. Processed data saved in Azure SQL")]
    S6 --> S7["7. Financial calculations and forecasting"]
    S7 --> S8["8. LangGraph coordinates three AI agents"]
    S8 --> S9["9. Final agent combines findings and generates insights"]
    S9 --> S10[("10. Evidence-backed report saved in Azure SQL")]
    S10 --> S11["11. React displays final results"]
```

## 3. LangGraph Agent Workflow

```mermaid
flowchart TD
    Start(["Research request"]) --> V["Validate company selection"]
    V --> F["Fetch and prepare data"]
    F --> A1["Financial Analysis and Forecasting Agent"]
    F --> A2["Business News Intelligence Agent"]
    A1 --> A3["Strategic Research and Decision Support Agent"]
    A2 --> A3
    A3 --> VE["Validate evidence and structured output"]
    VE --> SV["Save report and agent execution history"]
    SV --> Done(["Display results in React"])
```

## 4. Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant React
    participant FastAPI
    participant SEC as SEC API
    participant GDELT as GDELT API
    participant FA as Financial Agent
    participant NA as News Agent
    participant SA as Strategic Agent
    participant LLM as LLM API
    participant SQL as Azure SQL

    User->>React: Select company and start research
    React->>FastAPI: POST research request
    FastAPI->>FastAPI: Validate request
    FastAPI-->>React: Job accepted with job identifier
    FastAPI->>SEC: Request company facts
    SEC-->>FastAPI: Financial data
    FastAPI->>GDELT: Request news metadata
    GDELT-->>FastAPI: Article list
    FastAPI->>SQL: Store normalised data
    par Parallel analysis
        FastAPI->>FA: Run financial analysis
        FA->>SQL: Read financial data
        FA->>LLM: Interpret calculated results
        LLM-->>FA: Structured findings
        FA-->>FastAPI: Financial findings
    and
        FastAPI->>NA: Run news analysis
        NA->>SQL: Read news metadata
        NA->>LLM: Classify and summarise
        LLM-->>NA: Structured news findings
        NA-->>FastAPI: News findings
    end
    FastAPI->>SA: Combine financial and news findings
    SA->>LLM: Generate strategic insights
    LLM-->>SA: Structured insights
    SA-->>FastAPI: Final report content
    FastAPI->>SQL: Save report and execution history
    React->>FastAPI: Poll job status
    FastAPI-->>React: Completed report
    React-->>User: Display results
```

## 5. Component Descriptions

| Component | Responsibility | Input | Output | Communication |
|---|---|---|---|---|
| React frontend | User interface and visualisation | User actions, API responses | Requests, charts, reports | REST calls to FastAPI |
| FastAPI backend | API layer, job management | HTTP requests | JSON responses, job status | Frontend, services, database |
| Authentication and validation | Access control and input validation | Credentials, request bodies | Authorised, validated requests | Inside FastAPI |
| SEC EDGAR service | Retrieval of financial data | Company CIK | Raw XBRL facts, filing metadata | Called by backend |
| GDELT service | Retrieval of news metadata | Company query | Article metadata and URLs | Called by backend |
| Data processing service | Cleaning and normalisation | Raw API data | Normalised records | Writes to Azure SQL |
| Financial analysis service | Deterministic metrics | Stored financial records | Growth rates, margins, ratios | Used by financial agent |
| Forecasting service | Baseline and Statsmodels forecasts | Revenue history | Forecasts, intervals, evaluation metrics | Used by financial agent |
| LangGraph orchestration | Workflow control and shared state | Validated request | Agent outputs | Runs the three agents |
| Financial agent | Interpretation of calculated results | Metrics, forecasts | Structured financial findings | Strategic agent, LLM API |
| News agent | News classification and summarisation | News metadata | Categorised news, developments | Strategic agent, LLM API |
| Strategic agent | Synthesis and report content | Outputs of both agents | Insights, risks, opportunities | LLM API, report service |
| LLM API | Language interpretation | Structured prompts | Structured responses | Called by agents |
| Report generation | Assembling the evidence-referenced report | Strategic output | Stored report, PDF | Azure SQL, FastAPI |
| Azure SQL Database | Persistent storage | Records, reports, logs | Stored and queried data | Backend repositories |

## 6. End-to-End Request Flow

A user selects one to three companies and starts a research request in the React interface. FastAPI validates the request and creates a background job. The backend retrieves financial data from SEC EDGAR and news metadata from GDELT, normalises both, and stores them in Azure SQL. Python services then calculate financial metrics and forecasts. LangGraph runs the Financial Analysis and Forecasting Agent and the Business News Intelligence Agent in parallel. The Strategic Research and Decision Support Agent combines both outputs into insights, risks, opportunities and suggested investigation areas. The evidence is validated, the report and execution history are saved, and React displays the result.

No vector database or embeddings are used. The system works with structured financial data and news metadata.
