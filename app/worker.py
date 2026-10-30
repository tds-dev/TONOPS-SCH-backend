"""ソルバーワーカー: T_SolverRunResult の QUEUED をポーリングして実行する。

    python -m app.worker

API と並行して 1 つ以上起動する。実行の取得は条件付き UPDATE
（Status QUEUED → RUNNING）で行うため、複数ワーカーが同じ実行を取ることはない。
"""
import logging
import time

from sqlalchemy import select, update

from app import models  # noqa: F401
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.timeutil import utcnow
from app.engine.solve import execute_run
from app.models.transactions import SolverRun

# ワーカーの起動・計算開始・終了を記録する出力先。
log = logging.getLogger("scheduler.worker")


# 最も古い待機中の計算依頼を、他ワーカーとの重複を避けて取得する。
def claim_next(db) -> int | None:
    # 受付時刻と実行IDの順で探した、次に処理する計算依頼。
    run_id = db.scalar(
        select(SolverRun.RunID)
        .where(SolverRun.Status == "QUEUED")
        .order_by(SolverRun.RequestedAt, SolverRun.RunID)
        .limit(1)
    )
    if run_id is None:
        return None
    # 待機状態の依頼だけを実行中へ変更し、取得できた件数で競合を判定する。
    claimed = db.execute(
        update(SolverRun)
        .where(SolverRun.RunID == run_id, SolverRun.Status == "QUEUED")
        .values(Status="RUNNING", StartedAt=utcnow())
    )
    db.commit()
    return run_id if claimed.rowcount == 1 else None


# 計算依頼を繰り返し確認し、取得できた依頼を実行する。
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # 待機中の依頼がないとき、次の確認まで待つ秒数。
    poll = get_settings().worker_poll_seconds
    log.info("Solver worker started (poll every %.1fs)", poll)
    while True:
        with SessionLocal() as db:
            # 今回の確認で、このワーカーが取得できた計算依頼のID。
            run_id = claim_next(db)
            if run_id is not None:
                log.info("Run %s started", run_id)
                # 実行後の状態と計算エンジンの終了状態を持つ計算履歴。
                run = execute_run(db, run_id, SessionLocal)
                log.info("Run %s finished: %s / %s", run_id, run.Status, run.SolverStatus)
                continue
        time.sleep(poll)


if __name__ == "__main__":
    main()
