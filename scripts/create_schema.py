"""Create all tables in the database configured by DATABASE_URL.

    python -m scripts.create_schema            # create missing tables
    python -m scripts.create_schema --drop     # drop everything first (dev only!)
"""
import sys

from app import models  # noqa: F401
from app.core.db import Base, engine

if __name__ == "__main__":
    if "--drop" in sys.argv:
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")
    Base.metadata.create_all(engine)
    print(f"Created {len(Base.metadata.tables)} tables on {engine.url.render_as_string(hide_password=True)}")
