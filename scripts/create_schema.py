"""DATABASE_URL で指定した DB に全テーブルを作成する。

    python -m scripts.create_schema            # 未作成のテーブルを作成
    python -m scripts.create_schema --drop     # 先にすべて削除（開発用のみ！）
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
