from fastapi.testclient import TestClient
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core import database as database_module
from app.main import app


client = TestClient(app)


def test_sqlalchemy_imports_successfully():
    assert database_module.engine is not None
    assert database_module.Base is not None
    assert database_module.SessionLocal is not None


def test_engine_is_configured_for_postgresql():
    engine_url = database_module.engine.url

    assert engine_url.get_backend_name() == "postgresql"
    assert engine_url.get_driver_name() == "psycopg2"
    assert "sqlite" not in str(engine_url).lower()


def test_base_and_session_factory_exist():
    base_classes = [
        value
        for value in vars(database_module).values()
        if isinstance(value, type)
        and value.__module__ == database_module.__name__
        and issubclass(value, DeclarativeBase)
    ]

    assert len(base_classes) == 1
    assert base_classes[0] is database_module.Base
    assert database_module.Base.metadata is not None
    assert len(database_module.Base.metadata.tables) == 8

    session_factory_values = [
        value
        for value in vars(database_module).values()
        if isinstance(value, sessionmaker)
    ]
    assert len(session_factory_values) == 1
    assert session_factory_values[0] is database_module.SessionLocal


def test_health_endpoint_still_passes():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
