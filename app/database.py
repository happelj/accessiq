from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_database_settings

database_settings = get_database_settings()
DATABASE_URL = database_settings.database_url

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_kwargs = {"pool_pre_ping": database_settings.pool_pre_ping}

if database_settings.database_backend != "sqlite":
    engine_kwargs.update(
        pool_size=database_settings.pool_size,
        max_overflow=database_settings.max_overflow,
        pool_timeout=database_settings.pool_timeout,
        pool_recycle=database_settings.pool_recycle_seconds,
    )

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
