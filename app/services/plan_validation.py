"""計画期間・計画名の入力検証、拠点内の重複確認、コピー名の生成を定義する。"""
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.transactions import Plan


# 計画名の保存列に合わせた最大文字数。
PLAN_NAME_MAX_LENGTH = 100


# 分単位の計算に合わせ、新規作成・更新とも同じ期間制限を適用する。
def validate_plan_period(start_at: datetime, end_at: datetime) -> None:
    # 休日を含む開始から終了までの経過秒数。
    duration = (end_at - start_at).total_seconds()
    if duration < 60 or duration > 60 * 86400:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "終了日時は開始日時より1分以上後、計画期間は60日以内にしてください。",
        )


# 計画の状態にかかわらず、同じ拠点に同名の計画があるか確認する。
def _name_exists(db: Session, location_id: int, name: str, exclude_plan_id: int | None = None) -> bool:
    # 編集中の計画自身を除外し、現在の名前のまま他項目を変更できるようにする。
    statement = select(Plan.PlanID).where(Plan.LocationID == location_id, func.ltrim(func.rtrim(Plan.PlanName)) == name)
    if exclude_plan_id is not None:
        statement = statement.where(Plan.PlanID != exclude_plan_id)
    return db.scalar(
        statement.limit(1)
    ) is not None


# 計画名の空欄・文字数・拠点内の重複を確認し、前後の空白を除いた名前を返す。
def validate_plan_name(db: Session, location_id: int, name: str | None, exclude_plan_id: int | None = None) -> str:
    # 比較と保存に共通して使う、前後の空白を取り除いた名前。
    value = (name or "").strip()
    if not value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "計画名を入力してください")
    if len(value) > PLAN_NAME_MAX_LENGTH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "計画名は100文字以内で入力してください")
    if _name_exists(db, location_id, value, exclude_plan_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "同じ拠点に同じ計画名が存在します。別の計画名を入力してください")
    return value


# コピーを繰り返しても重複しないよう、元の名前にコピー用の連番を付ける。
def copy_plan_name(db: Session, location_id: int, source_name: str) -> str:
    # 空欄の既存計画でも、コピー先には名前を付ける。
    base = source_name.strip() or "計画"
    # 最初は「コピー」、2件目以降は「コピー2」「コピー3」とする。
    number = 1
    while True:
        # 接尾辞を含めて100文字に収まる候補名。
        suffix = f"（コピー{number if number > 1 else ''}）"
        candidate = base[:PLAN_NAME_MAX_LENGTH - len(suffix)] + suffix
        if not _name_exists(db, location_id, candidate):
            return candidate
        number += 1


# DBの重複禁止制約で同時登録が拒否された場合も、分かりやすい重複エラーを返す。
def flush_named_plan(db: Session, plan: Plan) -> None:
    # 失敗時の取り消しでオブジェクトの状態が変わっても、判定に必要な値を保持する。
    location_id, name = plan.LocationID, plan.PlanName
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if _name_exists(db, location_id, name):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "同じ拠点に同じ計画名が登録されました。別の計画名で再度実行してください",
            ) from None
        # 計画名以外の制約違反は、元のエラーとして扱う。
        raise
