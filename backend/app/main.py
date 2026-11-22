"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.database.base import Base
from app.database.session import get_engine, get_session_factory
from app.repositories.company_repository import CompanyRepository
from app.api.routes.companies import router as companies_router
from app.api.routes.refresh import router as refresh_router
from app.api.routes.research import router as research_router

# Import models so SQLAlchemy registers every table in Base.metadata.
from app.models.company import Company  # noqa: F401
from app.models.financial_record import FinancialRecord  # noqa: F401
from app.models.news_article import NewsArticle  # noqa: F401
from app.models.data_refresh_log import DataRefreshLog  # noqa: F401
from app.models.research_report import ResearchReport  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables and seed supported companies."""
    Base.metadata.create_all(bind=get_engine())

    session = get_session_factory()()
    try:
        repository = CompanyRepository(session)
        inserted = repository.seed_supported_companies()
        session.commit()
        app.state.seeded_companies = inserted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    yield


settings = get_settings()

app = FastAPI(
    title="AI Business Research and Growth Analysis API",
    description=(
        "Multi-agent business research API for financial analysis, "
        "revenue forecasting, news intelligence and strategic insights."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health_check():
    """Basic API liveness check."""
    return {
        "status": "healthy",
        "application": "AI Business Research and Growth Analysis API",
        "environment": settings.app_env,
    }


app.include_router(companies_router, prefix="/api/v1")

app.include_router(research_router, prefix="/api/v1")

app.include_router(refresh_router, prefix="/api/v1")
