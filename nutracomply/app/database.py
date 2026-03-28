from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

_pg_connect_args = {
    "connect_timeout": 10,
    "options": f"-c statement_timeout={settings.db_statement_timeout}",
}

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else _pg_connect_args,
    pool_pre_ping=not _is_sqlite,
    **({} if _is_sqlite else {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
    }),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
