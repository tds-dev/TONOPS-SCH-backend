"""フェーズ2: デモ工場の下書き計画を作成し、API 経由で計算する。"""
from datetime import timedelta

import pytest

from app.services.demo_seed import demo_start
from tests.conftest import FIXED_NOW

pytest.importorskip("ortools")


def iso(dt):
    return dt.isoformat() + "Z"


def make_plan(client, site_id, days=3, name="第44週・計画A"):
    start = demo_start(FIXED_NOW)
    r = client.post("/api/v1/plans", json={
        "siteId": site_id, "horizonStart": iso(start), "horizonEnd": iso(start + timedelta(days=days)),
        "planName": name,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_rule_types_listed(client):
    keys = [r["typeKey"] for r in client.get("/api/v1/rule-types").json()]
    assert "allowed_weekdays" in keys


def test_create_and_solve_demo_plan(client, seeded):
    plan = make_plan(client, seeded["siteId"])
    assert plan["status"] == "DRAFT"
    assert plan["planNo"] == "P-20261027-01"
    assert plan["basePlanId"] is None  # まだ MASTER はない

    r = client.post(f"/api/v1/plans/{plan['planId']}/solve", json={"wait": True, "timeLimitSec": 15})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "SUCCEEDED", run["errorMessage"]
    assert run["solverStatus"] in ("OPTIMAL", "FEASIBLE")
    assert run["taskCount"] == 21

    rows = client.get(f"/api/v1/plans/{plan['planId']}/assignments").json()
    assert len(rows) == 21
    assert all(row["startAt"].endswith("Z") for row in rows)

    violations = client.get(f"/api/v1/plans/{plan['planId']}/violations").json()
    assert [v for v in violations if v["severity"] == "HARD"] == []

    kpis = client.get(f"/api/v1/plans/{plan['planId']}/kpis").json()
    assert kpis["scheduled_tasks"] == 21 and kpis["unscheduled_tasks"] == 0

    # 実行中がなければ 2 回目の計算も可能。実行履歴は残る
    client.post(f"/api/v1/plans/{plan['planId']}/solve", json={"wait": True, "timeLimitSec": 5})
    assert len(client.get(f"/api/v1/plans/{plan['planId']}/solver-runs").json()) == 2


def test_queued_run_is_picked_by_worker_claim(client, seeded, db_session):
    from app.worker import claim_next

    plan = make_plan(client, seeded["siteId"], name="worker test")
    r = client.post(f"/api/v1/plans/{plan['planId']}/solve", json={"timeLimitSec": 5})
    assert r.status_code == 202 and r.json()["status"] == "QUEUED"
    # 待機中に 2 回目を依頼すると拒否される
    assert client.post(f"/api/v1/plans/{plan['planId']}/solve", json={}).status_code == 409
    run_id = claim_next(db_session)
    assert run_id == r.json()["runId"]
    assert claim_next(db_session) is None  # 他に待機中はない
