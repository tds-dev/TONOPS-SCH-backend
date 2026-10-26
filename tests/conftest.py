"""Test fixtures: an in-memory SQLite database per test, seeded with demo data."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.db import Base, get_db, make_engine
from app.main import app
from app.services.demo_seed import seed_demo

# Monday 2026-10-26 10:00 JST -> demo horizon starts Tuesday 06:00 JST
FIXED_NOW = datetime(2026, 10, 26, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


@pytest.fixture()
def db_session():
    engine = make_engine("sqlite://", poolclass=StaticPool)  # one shared in-memory connection
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def seeded(db_session):
    return seed_demo(db_session, now=FIXED_NOW)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
