import logging
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


def get_engine():
    db_url = settings.get_effective_database_url()
    if settings.ENVIRONMENT == "testing":
        return create_engine(db_url, connect_args={"check_same_thread": False})

    if db_url.startswith("sqlite"):
        return create_engine(db_url, connect_args={"check_same_thread": False}, echo=settings.DEBUG)

    try:
        eng = create_engine(
            db_url, pool_size=10, max_overflow=20, pool_pre_ping=True, echo=settings.DEBUG
        )
        # Verify connection
        with eng.connect():
            pass
        return eng
    except Exception as e:
        if settings.USE_SQLITE_FALLBACK:
            logger.warning(
                "Could not connect to PostgreSQL at %s (%s). Falling back to local SQLite at %s",
                db_url,
                type(e).__name__,
                settings.SQLITE_DB_PATH,
            )
            return create_engine(
                f"sqlite:///{settings.SQLITE_DB_PATH}", connect_args={"check_same_thread": False}
            )
        raise


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a SQLAlchemy session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
