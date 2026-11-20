# Technology Stack

| Layer | Technology | Reason | Access Requirement | Dependency / Risk | Fallback |
|---|---|---|---|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, Recharts | Component-based interface with typed code and interactive charts | None (open source) | Frontend and backend contract drift | Shared typed API schemas; OpenAPI documentation |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy | Asynchronous I/O, request validation, ORM, compatibility with data libraries | None | Version compatibility between packages | Pinned dependency versions |
| Multi-agent AI | LangGraph, Pydantic structured outputs | Controlled graph workflow with shared typed state and parallel execution | None | Framework API changes | Version pinning; sequential Python orchestration |
| LLM | Configurable hosted LLM API | Provider selected through environment variables | API key; usage may incur cost | Cost, rate limits, availability | Alternative provider; rule-based summaries when unavailable |
| Financial analysis | Pandas, NumPy, Statsmodels | Deterministic calculations and established time-series models | None | Limited history for some metrics | Baseline model; explicit insufficient-data message |
| Data source | SEC EDGAR API | Official, free public financial data | Identifying User-Agent; fair-access rate limit | Rate limits; tag differences between companies | Caching; tag mapping with alternatives |
| Data source | GDELT DOC API | Free news metadata and links | None | Relevance noise; no guaranteed full text | Query refinement; stored metadata; cached results |
| Database | Microsoft Azure SQL Database | Relational storage with constraints and Azure integration | Azure subscription | Subscription or permission restrictions | Local SQL Server container or SQLite for development |
| Version control | GitHub | Collaboration, review, CI integration | GitHub account | Token and permission handling | Local Git backup |
| Containerisation | Docker | Reproducible backend environment | Docker installation | Local setup differences | Virtual environment |
| CI/CD | GitHub Actions | Automated test and deployment pipelines | Repository permissions | Azure credential configuration | Manual deployment |
| Cloud | Microsoft Azure | Hosting, secrets and monitoring | Subscription or training credits | Cost and approvals | Local execution |
| Testing | Pytest, React Testing Library | Backend and frontend test coverage | None | Mocking of external APIs | Recorded sample responses |

## Rationale for React over Streamlit
Streamlit is suited to single-script data applications. The project requires a dedicated frontend and backend, versioned REST APIs, authentication, background research jobs, multi-page navigation and reusable components. React with FastAPI supports these requirements and a clear separation of responsibilities.

## Cost Considerations
SEC EDGAR and GDELT are free public data sources. Hosted LLM usage and Azure hosting may incur costs depending on available credits and service configuration. The application is designed to run locally without paid services except the chosen LLM provider.
