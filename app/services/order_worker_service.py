"""オーダー本体と担当作業者の追加・解除を、一つの保存処理で扱う。"""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.masters import Worker
from app.models.transactions import Order, OrderWorker
from app.services.order_service import sync_order_tasks
from app.services.order_validation import validate_order_write


def write_order(db: Session, original: Order | None, values: dict[str, Any], user: str) -> Order:
    """入力を検証して本体・担当リンクを更新し、新規登録・製品変更時はタスクも自動同期する。"""
    validate_order_write(db, original, values)
    # 新規登録時または製品を変更した編集時のみ、製品工程からタスクを自動生成・再生成する。
    product_changed = original is None or ("ProductID" in values and values["ProductID"] != original.ProductID)
    # 未送信と全解除を区別し、他項目だけの編集では担当リンクに触れない。
    worker_ids = values.pop("worker_ids", None)
    existing = {link.WorkerID: link for link in original.worker_links} if original else {}
    if worker_ids is not None:
        if len(worker_ids) != len(set(worker_ids)):
            raise HTTPException(422, "同じ作業者を重複して指定できません。")
        # 登録済みの参照は維持できるが、新しい指定は同じ拠点の有効な本人に限定する。
        location_id = original.LocationID if original else values.get("LocationID")
        valid_ids = set(db.scalars(select(Worker.WorkerID).where(
            Worker.LocationID == location_id, Worker.DeleteFlag == false(),
        )).all())
        if set(worker_ids) - existing.keys() - valid_ids:
            raise HTTPException(422, "同じ拠点の有効な作業者を指定してください。")

    # 担当リンクの検証を終えてから本体を更新し、部分保存を防ぐ。
    order = original if original is not None else Order(CreatedBy=user)
    for key, value in values.items():
        setattr(order, key, value)
    if original is not None:
        order.UpdatedBy = user
    db.add(order)
    if worker_ids is not None:
        # 残す行は再利用し、解除した行だけ削除する。追加分は親のOrderIDを引き継ぐ。
        order.worker_links = [
            existing[worker_id] if worker_id in existing else OrderWorker(WorkerID=worker_id)
            for worker_id in sorted(worker_ids)
        ]
    # 新規登録のOrderIDを確定させてから、製品工程に対応するタスクを同一トランザクションで生成する。
    if product_changed:
        db.flush()
        sync_order_tasks(db, order, user)
    return order
