"""Solver worker: polls T_SolverRuns for QUEUED runs and executes them.

    python -m app.worker

Run one or more alongside the API. A run is claimed with a conditional
UPDATE (Status QUEUED → RUNNING), so several workers never take the same run.
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

log = logging.getLogger("scheduler.worker")


def claim_next(db) -> int | None:
    run_id = db.scalar(
        select(SolverRun.RunID)
        .where(SolverRun.Status == "QUEUED")
        .order_by(SolverRun.RequestedAt, SolverRun.RunID)
        .limit(1)
    )
    if run_id is None:
        return None
    claimed = db.execute(
        update(SolverRun)
        .where(SolverRun.RunID == run_id, SolverRun.Status == "QUEUED")
        .values(Status="RUNNING", StartedAt=utcnow())
    )
    db.commit()
    return run_id if claimed.rowcount == 1 else None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    poll = get_settings().worker_poll_seconds
    log.info("Solver worker started (poll every %.1fs)", poll)
    while True:
        with SessionLocal() as db:
            run_id = claim_next(db)
            if run_id is not None:
                log.info("Run %s started", run_id)
                run = execute_run(db, run_id, SessionLocal)
                log.info("Run %s finished: %s / %s", run_id, run.Status, run.SolverStatus)
                continue
        time.sleep(poll)


if __name__ == "__main__":
    main()
