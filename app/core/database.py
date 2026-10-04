import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@db:5432/pip_db"


# Local development fallback only; production must provide DATABASE_URL.
DEVELOPMENT_DATABASE_URL = DEFAULT_DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", DEVELOPMENT_DATABASE_URL)


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
