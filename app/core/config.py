"""アプリケーション設定。環境変数または .env ファイルから読み込む。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 既定はローカルの SQL Server（Windows 認証）の TONOPS-SCH データベース
    database_url: str = (
        "mssql+pyodbc://@localhost/TONOPS-SCH"
        "?driver=ODBC+Driver+17+for+SQL+Server"
    )
    cors_origins: str = "http://localhost:4200"
    worker_poll_seconds: float = 2.0
    # 認証を導入するまでの CreatedBy / UpdatedBy の既定値
    default_user: str = "system"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
