"""製品工程・作業者の追加時に、同じ拠点の未登録担当リンクだけを作成する共通処理。"""
from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.masters import Product, ProductProcess, Worker, WorkerSkillMap


# 双方向の追加処理で、重複確認・担当不可の初期値・一括保存を共用する。
def _add_missing_skill_maps(db: Session, worker_ids: list[int], process_ids: list[int]) -> list[WorkerSkillMap]:
    if not worker_ids or not process_ids:
        return []
    # 登録済みの組合せを把握し、担当可否・日上限・備考を上書きしない。
    existing = set(db.execute(select(WorkerSkillMap.WorkerID, WorkerSkillMap.ProductProcessID).where(
        WorkerSkillMap.WorkerID.in_(worker_ids), WorkerSkillMap.ProductProcessID.in_(process_ids),
    )))
    # 呼出し元の仮データ登録では、この戻り値へ初期の担当値を設定する。
    added = [WorkerSkillMap(WorkerID=worker_id, ProductProcessID=process_id,
                           CanExecute=False, MaxDailyProcessQuantity=None)
             for worker_id in worker_ids for process_id in process_ids if (worker_id, process_id) not in existing]
    db.add_all(added)
    # 次の呼出しでも今回分を検出できるよう、確定せず保存内容を反映する。
    db.flush()
    return added


# 工程の追加時に、同じ拠点の作業者との不足する担当関係を作る。
def add_worker_skill_maps(db: Session, process: ProductProcess) -> list[WorkerSkillMap]:
    # 自動採番された工程IDを、リンクの参照先として確定する。
    db.flush()
    # 工程の製品から、作業者を抽出する所属拠点を取得する。
    product = db.get(Product, process.ProductID)
    if product is None or product.DeleteFlag:
        raise HTTPException(422, "作業者工程リンクには有効な製品の工程を指定してください。")
    # 同じ拠点で削除されていない作業者だけを、新しい工程の候補として登録する。
    worker_ids = list(db.scalars(
        select(Worker.WorkerID).where(Worker.LocationID == product.LocationID, Worker.DeleteFlag == false())
        .order_by(Worker.WorkerID)
    ))
    return _add_missing_skill_maps(db, worker_ids, [process.ProductProcessID])


# 作業者の追加時に、同じ拠点の全製品工程との担当関係を担当不可で作る。
def add_process_skill_maps(db: Session, worker: Worker) -> list[WorkerSkillMap]:
    # 新規作業者の自動採番IDを担当関係から参照できるようにする。
    db.flush()
    # 削除済み作業者には新しい担当関係を作らない。
    if worker.DeleteFlag:
        return []
    # 削除されていない同じ拠点の製品に属する工程だけを対象とする。
    process_ids = list(db.scalars(select(ProductProcess.ProductProcessID).join(
        Product, Product.ProductID == ProductProcess.ProductID,
    ).where(Product.LocationID == worker.LocationID, Product.DeleteFlag == false())
      .order_by(ProductProcess.ProductProcessID)))
    return _add_missing_skill_maps(db, [worker.WorkerID], process_ids)
