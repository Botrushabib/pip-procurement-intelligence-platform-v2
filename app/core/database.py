from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@db:5432/pip_db"


class Base(DeclarativeBase):
    pass


engine = create_engine(DEFAULT_DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
