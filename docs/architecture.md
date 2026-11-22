# Architecture

## 1. Component Architecture

```mermaid
flowchart LR
    subgraph sg1[Users]
        U[Analyst]
    end

    subgraph sg2[Application]
        FE[React Dashboard<br/>planned]
        API[FastAPI Backend]
        DB[SQLite Database]
    end

    subgraph sg3[Public Data Sources]
        SEC[SEC EDGAR<br/>financial filings]
        GD[NewsData.io<br/>business news]
    end

    subgraph sg4[Analysis and AI]
        CALC[Python Analysis<br/>and Forecasting]
        AG[Three AI Agents<br/>LangGraph]
        LLM[LLM API]
    end

    U -->|selects company| FE
    FE -->|request| API
    SEC -->|financial data| API
    GD -->|news links| API
    API -->|stores data| DB
    DB -->|data| CALC
    CALC -->|metrics and forecasts| AG
    AG -.->|interpretation| LLM
    AG -->|research report| DB
    DB -->|stored report| API
    API -->|results| FE

    classDef user fill:#E8F1FB,stroke:#2B6CB0,color:#1A365D
    classDef app fill:#E6FFFA,stroke:#2C7A7B,color:#234E52
    classDef data fill:#FFF5E6,stroke:#C05621,color:#7B341E
    classDef ai fill:#F3E8FF,stroke:#6B46C1,color:#44337A
    class U user
    class FE,API,DB app
    class SEC,GD data
    class CALC,AG,LLM ai
```

## 2. Data Flow

```mermaid
flowchart LR
    S1[Step 1<br/>Select company] --> S2[Step 2<br/>Collect SEC and news data]
    S2 --> S3[Step 3<br/>Clean and store data]
    S3 --> S4[Step 4<br/>Calculate growth<br/>and forecasts]
    S4 --> S5[Step 5<br/>AI agents<br/>analyse findings]
    S5 --> S6[Step 6<br/>Save and display<br/>research report]

    classDef step fill:#E8F1FB,stroke:#2B6CB0,color:#1A365D
    classDef final fill:#E6FFFA,stroke:#2C7A7B,color:#234E52
    class S1,S2,S3,S4,S5 step
    class S6 final
```

## 3. LangGraph Agent Workflow

```mermaid
flowchart TD
    Start[Research request] --> Prep[Validate request<br/>and prepare data]

    subgraph sg1[Run sequentially]
        FA[Financial Agent<br/>numbers and forecasts]
        NA[News Agent<br/>headlines and developments]
    end

    Prep --> FA
    FA --> NA
    NA --> SA[Strategic Agent<br/>combines both findings]
    SA --> Check[Evidence check]
    Check --> Out[Save and display report]

    classDef agent fill:#F3E8FF,stroke:#6B46C1,color:#44337A
    classDef step fill:#E8F1FB,stroke:#2B6CB0,color:#1A365D
    classDef final fill:#E6FFFA,stroke:#2C7A7B,color:#234E52
    class FA,NA,SA agent
    class Start,Prep,Check step
    class Out final
```

## 4. Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant React
    participant FastAPI
    participant SEC as SEC API
    participant NEWS as NewsData.io API
    participant FA as Financial Agent
    participant NA as News Agent
    participant SA as Strategic Agent
    participant LLM as LLM API
    participant SQL as SQLite

    User->>React: Select company and start research
    React->>FastAPI: POST research request
    FastAPI->>FastAPI: Validate request
    FastAPI->>SEC: Request company facts
    SEC-->>FastAPI: Financial data
    FastAPI->>NEWS: Request news metadata
    NEWS-->>FastAPI: Article list
    FastAPI->>SQL: Store normalised data
        FastAPI->>FA: Run financial analysis
        FA->>SQL: Read financial data
        FA->>LLM: Interpret calculated results
        LLM-->>FA: Structured findings
        FA-->>FastAPI: Financial findings
        FastAPI->>NA: Run news analysis
        NA->>SQL: Read news metadata
        NA->>LLM: Classify and summarise
        LLM-->>NA: Structured news findings
        NA-->>FastAPI: News findings
    FastAPI->>SA: Combine financial and news findings
    SA->>LLM: Generate strategic insights
    LLM-->>SA: Structured insights
    SA-->>FastAPI: Final report content
    FastAPI->>SQL: Save report and execution history
    FastAPI-->>React: Completed report (synchronous response)
    React-->>User: Display results
```

## 5. Component Descriptions

| Component | Responsibility | Input | Output | Communication |
|---|---|---|---|---|
| React frontend | User interface and visualisation | User actions, API responses | Requests, charts, reports | REST calls to FastAPI |
| FastAPI backend | API layer and request handling | HTTP requests | JSON responses, job status | Frontend, services, database |
| Request validation | Input validation (authentication planned) | Request bodies | Validated requests | Inside FastAPI |
| SEC EDGAR service | Retrieval of financial data | Company CIK | Raw XBRL facts, filing metadata | Called by backend |
| NewsData.io service | Retrieval of news metadata | Company query | Article metadata and URLs | Called by backend |
| Data processing service | Cleaning and normalisation | Raw API data | Normalised records | Writes to SQLite |
| Financial analysis service | Deterministic metrics | Stored financial records | Growth rates, margins, ratios | Used by financial agent |
| Forecasting service | Baseline and Statsmodels forecasts | Revenue history | Forecasts, intervals, evaluation metrics | Used by financial agent |
| LangGraph orchestration | Workflow control and shared state | Validated request | Agent outputs | Runs the three agents |
| Financial agent | Interpretation of calculated results | Metrics, forecasts | Structured financial findings | Strategic agent, LLM API |
| News agent | News classification and summarisation | News metadata | Categorised news, developments | Strategic agent, LLM API |
| Strategic agent | Synthesis and report content | Outputs of both agents | Insights, risks, opportunities | LLM API, report service |
| LLM API | Language interpretation | Structured prompts | Structured responses | Called by agents |
| Report storage | Saving the evidence-referenced report | Workflow output | Stored JSON report (PDF planned) | SQLite, FastAPI |
| SQLite database (Azure SQL planned) | Persistent storage | Records, reports, logs | Stored and queried data | Backend repositories |

## 6. End-to-End Request Flow

A client (the React interface is planned) sends a research request for a supported company, and FastAPI validates the ticker against the central company configuration. Financial data from SEC EDGAR and news metadata from NewsData.io are collected by a separate refresh endpoint, normalised and stored in SQLite. For a research request, Python services calculate financial metrics and a SARIMAX revenue forecast with a rolling backtest. LangGraph then runs the Financial Analysis and Forecasting Agent, the Business News Intelligence Agent and the Strategic Research and Decision Support Agent sequentially, pausing between agents to respect LLM rate limits. Evidence URLs are restricted to backend data, the report is saved, and the result is returned as JSON.

No vector database or embeddings are used. The system works with structured financial data and news metadata.
