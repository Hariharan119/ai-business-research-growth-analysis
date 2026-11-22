"""Company information endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.repositories.company_repository import CompanyRepository
from app.schemas.company import CompanyRead

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get("", response_model=list[CompanyRead])
def list_companies(session: Session = Depends(get_db)):
    """Return all active supported companies."""
    repository = CompanyRepository(session)
    return repository.list_active()


@router.get("/{ticker}", response_model=CompanyRead)
def get_company(ticker: str, session: Session = Depends(get_db)):
    """Return a supported company by ticker."""
    repository = CompanyRepository(session)
    company = repository.get_by_ticker(ticker)

    if company is None or not company.is_active:
        raise HTTPException(
            status_code=404,
            detail=f"Company '{ticker.upper()}' was not found.",
        )

    return company
