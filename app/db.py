from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for future SQLAlchemy models."""


def create_db_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, future=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=create_db_engine())
