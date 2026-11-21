"""SQLAlchemy engine and session management."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_database_engine():
    settings = get_settings()
    database_url = settings.database_url

    connect_args = {}

    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_engine():
    return create_database_engine()


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
