"""製品工程の追加・番号交換・削除を、重複しない連番としてまとめて保存する処理。"""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import Product, ProductProcess
from app.models.transactions import Task
from app.services.product_validation import validate_product_process_write
from app.services.worker_process_service import add_worker_process_links


# 同じ製品の並べ替えを直列化し、保存済み工程を現在の番号順で取得する。
def _locked_processes(db: Session, product_id: int) -> list[ProductProcess]:
    # SQL Serverでは製品行を更新用にロックし、工程が0件の場合も同時追加の競合を防ぐ。
    product = db.scalar(select(Product.ProductID).where(Product.ProductID == product_id)
                        .with_hint(Product, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql"))
    if product is None:
        raise HTTPException(422, "有効な製品を指定してください。")
    return list(db.scalars(select(ProductProcess).where(ProductProcess.ProductID == product_id)
                          .order_by(ProductProcess.SequenceNumber, ProductProcess.ProductProcessID)
                          .execution_options(populate_existing=True)))


# 一時的な負数へ退避してから正しい番号を付け、一意制約を維持して入れ替える。
def _assign_numbers(db: Session, positions: list[tuple[ProductProcess, int]], user: str) -> None:
    # 番号を変更する工程だけを保存対象にし、移動しない工程の更新履歴を保つ。
    changes = [(process, number) for process, number in positions if process.SequenceNumber != number]
    for temporary, (process, _) in enumerate(changes, start=1):
        process.SequenceNumber = -temporary
    db.flush()
    for process, number in changes:
        process.SequenceNumber = number
        process.UpdatedBy = user
    db.flush()


# 新規工程は指定位置へ挿入し、既存工程の番号変更は移動先の工程と交換する。
def save_product_process(db: Session, original: ProductProcess | None, values: dict[str, Any], user: str) -> ProductProcess:
    # 工程の所属先は更新で変更できない。全工程の更新を同じ製品行のロックで保護する。
    product_id = original.ProductID if original is not None else values.get("ProductID")
    processes = _locked_processes(db, product_id)
    if original is not None and original not in processes:
        raise HTTPException(404, "対象の工程は削除されています。工程一覧を再読込してください。")
    validate_product_process_write(db, original, values)
    # 新規は末尾まで指定でき、既存は現在の工程数まで指定できる。
    maximum = len(processes) + (1 if original is None else 0)
    current = processes.index(original) + 1 if original is not None else maximum
    target = values.get("SequenceNumber", current)
    if not 1 <= target <= maximum:
        raise HTTPException(422, f"工程番号は1～{maximum}で指定してください。")
    if original is None:
        # 挿入位置を空け、後続工程を一つずつ後ろへ送る。
        positions = [(process, index if index < target else index + 1)
                     for index, process in enumerate(processes, start=1)]
        _assign_numbers(db, positions, user)
        original = ProductProcess(**{**values, "SequenceNumber": target}, CreatedBy=user)
        db.add(original)
        # 同じ拠点の全作業者との担当関係を作り、初期値は担当不可とする。
        add_worker_process_links(db, original)
    else:
        # 変更した工程を指定番号へ移し、その位置の工程を元の位置へ戻す。
        processes[current - 1], processes[target - 1] = processes[target - 1], processes[current - 1]
        _assign_numbers(db, list(zip(processes, range(1, len(processes) + 1))), user)
        for key, value in values.items():
            setattr(original, key, value)
        original.UpdatedBy = user
    return original


# タスクの生成元を保護し、削除後の工程番号を1から詰め直す。
def delete_product_process(db: Session, original: ProductProcess, user: str) -> None:
    # ロック取得後の最新工程一覧と、この工程を参照する既存タスク。
    processes = _locked_processes(db, original.ProductID)
    if original not in processes:
        raise HTTPException(404, "対象の工程は削除されています。工程一覧を再読込してください。")
    used = db.scalar(select(Task.TaskID).where(Task.ProductProcessID == original.ProductProcessID).limit(1))
    if used is not None:
        raise HTTPException(409, "既存タスクから参照されている工程は削除できません。")
    processes.remove(original)
    db.delete(original)
    db.flush()
    _assign_numbers(db, list(zip(processes, range(1, len(processes) + 1))), user)
