"""デモデータを登録する（1 工場、設備 6 台、ジョブ 7 件）。

    python -m scripts.seed_demo
"""
from app import models  # noqa: F401
from app.core.db import Base, SessionLocal, engine
from app.models.masters import Organization
from app.services.demo_seed import seed_demo
from scripts.create_database import ensure_database

if __name__ == "__main__":
    ensure_database()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(Organization).filter_by(OrganizationCode="DEMO").first():
            print("Demo data already present. Run `python -m scripts.create_schema --drop` to reset.")
        else:
            print("Seeded:", seed_demo(db))
