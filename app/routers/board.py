"""計画ボード、手動編集、計画比較、配台表（フェーズ3）。

ボードと配台表の時刻は拠点の現地時刻（オフセットなし）。編集リクエストの
オフセットなしの日時も拠点の現地時刻として解釈する。
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.engine.result import Violation
from app.models.transactions import Plan
from app.routers.deps import current_user
from app.schemas.base import ApiModel
from app.services.board_service import build_board
from app.services.compare_service import compare_plans, dispatch_list
from app.services.edit_service import ChangeRequest, evaluate_edit, save_edit

router = APIRouter(tags=["Board"])


# 画面から送信する一件の割付変更。
class AssignmentChange(ApiModel):
    assignment_id: int | None = None  # 既存の割付（ボードのイベント ID）
    task_id: int | None = None  # 未割付タスクを配置する場合
    resource_id: int | None = None
    start_at: datetime | None = None  # オフセットなしは拠点の現地時刻
    end_at: datetime | None = None  # 指定時はリサイズ。省略時は所要時間を維持
    is_locked: bool | None = None
    remove: bool = False  # 割付を外す
    row_ver: int | None = None  # 楽観的排他制御（ボードの rowVer をそのまま返す）


# 割付変更の一覧と、移動した作業の固定設定。
class EditBody(ApiModel):
    changes: list[AssignmentChange]
    lock_moved: bool = True  # 手動で動かしたタスクをロックする（再計算で動かさない）
    force: bool = False  # 必須制約の違反があっても保存する


# 手動編集で検出した制約違反の応答項目。
class ViolationOut(ApiModel):
    severity: str
    code: str
    message: str
    task_id: int | None = None
    rule_id: int | None = None


# 手動編集の検証結果・違反・評価値の応答項目。
class EditOut(ApiModel):
    ok: bool
    errors: list[str]
    hard: list[ViolationOut]
    soft: list[ViolationOut]
    kpis: dict[str, float]
    changed_task_ids: list[int]


# 計画を取得し、存在しない場合は見つからない理由を返す。
def _plan_or_404(db: Session, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(404, f"計画 {plan_id} が見つかりません")
    return plan


# APIで受け取った割付編集を、検証処理へ渡す形式にする。
def _requests(body: EditBody) -> list[ChangeRequest]:
    return [ChangeRequest(**c.model_dump()) for c in body.changes]


# 手動編集の検証結果を、APIの応答形式へ変換する。
def _out(result) -> EditOut:
    # 一件の制約違反をAPIの応答形式へ変換する。
    def v(x: Violation) -> ViolationOut:
        return ViolationOut(severity=x.severity, code=x.code, message=x.message, task_id=x.task_id, rule_id=x.rule_id)

    return EditOut(ok=result.ok, errors=result.errors, hard=[v(x) for x in result.hard],
                   soft=[v(x) for x in result.soft], kpis=result.kpis, changed_task_ids=result.changed_task_ids)


@router.get("/plans/compare")
def get_compare(a: int, b: int, db: Session = Depends(get_db)):
    """計画 A と B の KPI 差分と、割付に違いのあるタスク。"""
    return compare_plans(db, a, b)


@router.get("/plans/{plan_id}/board")
def get_board(
    plan_id: int,
    start: datetime | None = Query(None, alias="from"),
    end: datetime | None = Query(None, alias="to"),
    resource_group_id: int | None = Query(None, alias="resourceGroupId"),
    color_by: str | None = Query(None, alias="colorBy"),
    db: Session = Depends(get_db),
):
    """DayPilot Scheduler 用のボードデータ（リソース、イベント、段取り、非稼働時間、未割付タスク、課題、KPI）。"""
    return build_board(db, _plan_or_404(db, plan_id), start, end, resource_group_id, color_by)


@router.post("/plans/{plan_id}/assignments/validate", response_model=EditOut)
def post_validate(plan_id: int, body: EditBody, db: Session = Depends(get_db)):
    """変更を保存せずに検証する。ドロップ時に呼び、必須違反なら元に戻す。"""
    result, *_ = evaluate_edit(db, _plan_or_404(db, plan_id), _requests(body), body.lock_moved)
    db.rollback()
    return _out(result)


@router.patch("/plans/{plan_id}/assignments", response_model=EditOut)
def patch_assignments(plan_id: int, body: EditBody, db: Session = Depends(get_db), user: str = Depends(current_user)):
    """移動・リサイズ・ロック・解除・配置・割付解除を保存し、KPI と課題を再計算する。"""
    result = save_edit(db, _plan_or_404(db, plan_id), _requests(body), user, body.lock_moved, body.force)
    return _out(result)


@router.get("/dispatch")
def get_dispatch(
    # 取得・作成の対象となる拠点の識別番号。
    location_id: int = Query(..., alias="locationId"),
    day: date = Query(..., alias="date"),
    resource_group_id: int | None = Query(None, alias="resourceGroupId"),
    db: Session = Depends(get_db),
):
    """配台表: マスタ計画の指定日（現地時間）の割付をリソース別・開始順に返す。"""
    return dispatch_list(db, location_id, day, resource_group_id)
