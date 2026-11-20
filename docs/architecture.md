# Architecture

## 1. Component Architecture

```mermaid
flowchart TB
    subgraph PRES [Presentation Layer]
        USER[Analyst User]
        FE[React Frontend<br/>TypeScript, Vite, Tailwind, Recharts, TanStack Query]
    end

    subgraph APIL [API Layer - FastAPI]
        GW[Versioned REST API and OpenAPI Docs]
        MW[JWT Authentication, Rate Limiting and Request Validation]
        JOBS[Background Job Manager and Status Tracking]
    end

    subgraph EXT [External Public Data Sources]
        SEC[SEC EDGAR API<br/>companyfacts and submissions]
        GDELT[GDELT DOC API<br/>article metadata and links]
    end

    subgraph ING [Data Ingestion Layer]
        SECC[SEC Client<br/>User-Agent, rate limiting, caching]
        GDC[GDELT Client<br/>retry, timeout handling, deduplication]
        NORM[Normalisation Service<br/>XBRL tag mapping and period alignment]
    end

    subgraph PERS [Persistence Layer]
        REPO[Repositories<br/>SQLAlchemy and Alembic migrations]
        DB[Azure SQL Database<br/>financials, news, forecasts, changes, reports, agent logs]
    end

    subgraph ANA [Deterministic Analytics Layer - Python]
        FIN[Financial Analysis Service<br/>Pandas and NumPy growth, margins, ratios]
        FCST[Forecasting Service<br/>baseline vs Statsmodels, backtesting, intervals]
        CHG[Change Detection Engine<br/>configurable thresholds]
        RULE[Rule-based Risk and Opportunity Signals]
    end

    subgraph ORCH [AI Orchestration Layer - LangGraph]
        STATE[Shared Typed State<br/>Pydantic models]
        A1[Agent 1<br/>Financial Analysis and Forecasting]
        A2[Agent 2<br/>Business News Intelligence]
        A3[Agent 3<br/>Strategic Research and Decision Support]
        VAL[Evidence and Structured Output Validation]
    end

    LLM[Configurable LLM Provider<br/>selected through environment variables]

    subgraph REPG [Reporting Layer]
        RGEN[Research Report Generator<br/>evidence references]
        PDF[PDF Export]
    end

    subgraph OPS [Cloud and DevOps]
        KV[Azure Key Vault]
        INS[Azure Application Insights]
        GH[GitHub Actions CI/CD]
        DOCK[Docker Container]
    end

    USER --> FE
    FE -->|HTTPS REST| GW
    GW --> MW
    MW --> JOBS

    JOBS --> SECC
    JOBS --> GDC
    SECC <-->|HTTPS| SEC
    GDC <-->|HTTPS| GDELT
    SECC --> NORM
    GDC --> NORM
    NORM --> REPO
    REPO <--> DB

    DB --> FIN
    FIN --> FCST
    FIN --> RULE
    DB --> CHG
    CHG --> RULE

    JOBS -->|start workflow| STATE
    STATE -->|parallel| A1
    STATE -->|parallel| A2
    FIN --> A1
    FCST --> A1
    RULE --> A1
    DB --> A2
    A1 --> A3
    A2 --> A3
    CHG --> A3
    A1 -.-> LLM
    A2 -.-> LLM
    A3 -.-> LLM

    A3 --> VAL
    VAL --> RGEN
    RGEN --> PDF
    RGEN -->|save report and execution history| REPO
    RGEN -->|report and PDF| GW

    KV -.->|secrets| GW
    INS -.->|logs and metrics| GW
    GH -->|build and deploy| DOCK
    DOCK -.->|hosts| GW

    classDef ext fill:#fff3e0,stroke:#e65100,color:#000
    classDef ai fill:#e8eaf6,stroke:#283593,color:#000
    classDef store fill:#e0f2f1,stroke:#00695c,color:#000
    classDef ops fill:#f3e5f5,stroke:#6a1b9a,color:#000
    class SEC,GDELT,LLM ext
    class STATE,A1,A2,A3,VAL ai
    class DB,REPO store
    class KV,INS,GH,DOCK ops
```

## 2. Data Flow

```mermaid
flowchart TD
    S1[Step 1 - User selects a company] --> S2[Step 2 - React sends request to FastAPI]
    S2 --> S3[Step 3 - FastAPI validates the request]
    S3 --> S4[Step 4 - Backend retrieves SEC financial data and GDELT news]
    S4 --> S5[Step 5 - Data is cleaned and normalised]
    S5 --> S6[Step 6 - Processed data saved in Azure SQL]
    S6 --> S7[Step 7 - Financial calculations and forecasting]
    S7 --> S8[Step 8 - LangGraph coordinates three AI agents]
    S8 --> S9[Step 9 - Final agent combines findings and generates insights]
    S9 --> S10[Step 10 - Evidence-backed report saved in Azure SQL]
    S10 --> S11[Step 11 - React displays final results]
```

## 3. LangGraph Agent Workflow

```mermaid
flowchart TD
    Start[Research request] --> V[Validate company selection]
    V --> F[Fetch and prepare data]
    F --> A1[Financial Analysis and Forecasting Agent]
    F --> A2[Business News Intelligence Agent]
    A1 --> A3[Strategic Research and Decision Support Agent]
    A2 --> A3
    A3 --> VE[Validate evidence and structured output]
    VE --> SV[Save report and agent execution history]
    SV --> Done[Display results in React]
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
