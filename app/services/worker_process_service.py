"""製品工程の追加時に、同じ拠点の全作業者との未登録担当リンクを作成する処理。"""
from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.masters import Product, ProductProcess, Worker, WorkerProcessLink


# 既存の担当可否・日上限を保持し、足りない組合せだけを担当不可で追加する。
def add_worker_process_links(db: Session, process: ProductProcess) -> list[WorkerProcessLink]:
    # 自動採番された工程IDを、リンクの参照先として確定する。
    db.flush()
    # 工程の製品から、作業者を抽出する所属拠点を取得する。
    product = db.get(Product, process.ProductID)
    if product is None or product.DeleteFlag:
        raise HTTPException(422, "作業者工程リンクには有効な製品の工程を指定してください。")
    # 登録済み作業者を把握し、再実行しても担当設定を上書きしない。
    existing_worker_ids = set(db.scalars(
        select(WorkerProcessLink.WorkerID).where(WorkerProcessLink.ProductProcessID == process.ProductProcessID)
    ))
    # 同じ拠点で削除されていない作業者だけを、新しい工程の候補として登録する。
    workers = db.scalars(
        select(Worker).where(Worker.LocationID == product.LocationID, Worker.DeleteFlag == false())
        .order_by(Worker.WorkerID)
    )
    # 今回追加したリンク。呼出し元の仮データ登録では、この戻り値へ担当値を設定する。
    added = [WorkerProcessLink(WorkerID=worker.WorkerID, ProductProcessID=process.ProductProcessID,
                               CanExecute=False, MaxDailyQuantity=None)
             for worker in workers if worker.WorkerID not in existing_worker_ids]
    db.add_all(added)
    # 次の呼出しから今回分も登録済みとして確認できるよう、確定せず保存内容を反映する。
    db.flush()
    return added
