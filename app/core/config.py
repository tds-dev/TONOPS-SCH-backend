"""アプリケーション設定。環境変数または .env ファイルから読み込む。"""
from functools import lru_cache
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


# 接続先・認証前の操作者名・アプリ共通の日本時間をまとめる設定。
class Settings(BaseSettings):
    # 環境変数とUTF-8の設定ファイルを読み込む設定。
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 既定はローカルの SQL Server（Windows 認証）の TONOPS-SCH データベース
    database_url: str = (
        "mssql+pyodbc://@localhost/TONOPS-SCH"
        "?driver=ODBC+Driver+17+for+SQL+Server"
    )
    cors_origins: str = "http://localhost:4200"
    worker_poll_seconds: float = 2.0
    # フロントと共通の日本時間。環境変数で上書きせず、表示・入力のずれを防ぐ。
    app_timezone: ClassVar[str] = "Asia/Tokyo"
    # 認証を導入するまでの CreatedBy / UpdatedBy の既定値
    default_user: str = "system"

    @property
    def cors_origin_list(self) -> list[str]:
        # カンマ区切りの接続許可先を、空欄を除いた一覧へ変換する。
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    # 設定を一度だけ読み込み、各処理から同じ値を参照する。
    return Settings()
