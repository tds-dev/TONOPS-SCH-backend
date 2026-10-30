"""フェーズ3: ボード、手動編集、承認と置換、比較、配台表、SSE。"""
from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.services.demo_seed import demo_start
from tests.conftest import FIXED_NOW

pytest.importorskip("ortools")

API = "/api/v1"


def iso(dt):
    return dt.isoformat() + "Z"


def solved_plan(client, site_id, offset_days=0, days=3, name="計画"):
    start = demo_start(FIXED_NOW) + timedelta(days=offset_days)
    plan = client.post(f"{API}/plans", json={
        "siteId": site_id, "horizonStart": iso(start), "horizonEnd": iso(start + timedelta(days=days)), "planName": name,
    }).json()
    run = client.post(f"{API}/plans/{plan['planId']}/solve", json={"wait": True, "timeLimitSec": 10}).json()
    assert run["status"] == "SUCCEEDED", run["errorMessage"]
    return plan


def two_on_same_resource(board):
    by_res = {}
    for e in board["events"]:
        by_res.setdefault(e["resource"], []).append(e)
    rows = next(v for v in by_res.values() if len(v) >= 2)
    return sorted(rows, key=lambda e: e["start"])[:2]


def test_board_shape(client, seeded):
    plan = solved_plan(client, seeded["siteId"])
    board = client.get(f"{API}/plans/{plan['planId']}/board").json()
    assert board["timeZone"] == "Asia/Tokyo" and board["colorBy"] == "family"
    assert board["from"] == "2026-10-27T06:00:00"  # 現地時刻・オフセットなし
    assert len(board["resources"]) == 6 and [g["name"] for g in board["groups"]] == ["配合", "充填", "包装"]
    assert len(board["events"]) == 21
    e = board["events"][0]
    assert {"id", "resource", "start", "end", "text", "rowVer", "colorValue", "isLocked"} <= set(e)
    assert not e["start"].endswith("Z")
    # 昼休み 12:00–13:00 が非稼働として返る
    assert any(n["start"].endswith("T12:00:00") and n["end"].endswith("T13:00:00") for n in board["nonWorking"])
    assert board["unscheduled"] == []
    assert "late_orders" in board["kpis"]


def test_validate_and_save_moves(client, seeded):
    plan = solved_plan(client, seeded["siteId"])
    pid = plan["planId"]
    board = client.get(f"{API}/plans/{pid}/board").json()
    first, second = two_on_same_resource(board)

    # 2 件目を 1 件目と同じ開始時刻へ → 重なり（必須違反）
    clash = {"changes": [{"assignmentId": second["id"], "startAt": first["start"], "rowVer": second["rowVer"]}]}
    v = client.post(f"{API}/plans/{pid}/assignments/validate", json=clash).json()
    assert v["ok"] is False and "OVERLAP" in [x["code"] for x in v["hard"]]
    assert client.patch(f"{API}/plans/{pid}/assignments", json=clash).status_code == 422

    # 古い rowVer は 409
    stale = {"changes": [{"assignmentId": second["id"], "isLocked": True, "rowVer": second["rowVer"] + 5}]}
    assert client.patch(f"{API}/plans/{pid}/assignments", json=stale).status_code == 409

    # 外して、同じ位置に戻す → 手動・ロック済みになる
    task_id = second["taskId"]
    r = client.patch(f"{API}/plans/{pid}/assignments", json={"changes": [{"assignmentId": second["id"], "remove": True}]})
    assert r.status_code == 200, r.text
    after = client.get(f"{API}/plans/{pid}/board").json()
    assert [u["taskId"] for u in after["unscheduled"]] == [task_id]
    place = {"changes": [{"taskId": task_id, "resourceId": second["resource"], "startAt": second["start"]}]}
    r = client.patch(f"{API}/plans/{pid}/assignments", json=place)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    placed = next(e for e in client.get(f"{API}/plans/{pid}/board").json()["events"] if e["taskId"] == task_id)
    assert placed["source"] == "MANUAL" and placed["isLocked"] is True and placed["start"] == second["start"]

    # force=true なら違反があっても保存でき、課題一覧に載る
    clash["changes"][0]["assignmentId"] = placed["id"]
    clash["changes"][0]["rowVer"] = placed["rowVer"]
    clash["changes"][0]["isLocked"] = False
    clash["force"] = True
    assert client.patch(f"{API}/plans/{pid}/assignments", json=clash).status_code == 200
    issues = client.get(f"{API}/plans/{pid}/board").json()["issues"]
    assert any(i["code"] == "OVERLAP" for i in issues)


def test_approve_supersede_compare_dispatch(client, seeded):
    site = seeded["siteId"]
    a = solved_plan(client, site, name="A")
    r = client.post(f"{API}/plans/{a['planId']}/approve")
    assert r.status_code == 200 and r.json()["status"] == "MASTER"
    assert client.post(f"{API}/plans/{a['planId']}/approve").status_code == 409  # 既にマスタ
    orders = client.get(f"{API}/orders", params={"siteId": site}).json()
    assert {j["status"] for j in orders} == {"PLANNED"}

    b = solved_plan(client, site, offset_days=1, name="B")  # 翌日開始、元計画 = A
    assert b["basePlanId"] == a["planId"]
    client.post(f"{API}/plans/{b['planId']}/approve")
    a_now = client.get(f"{API}/plans/{a['planId']}").json()
    assert a_now["status"] == "SUPERSEDED" and a_now["supersededAt"] == b["horizonStart"]

    c = solved_plan(client, site, offset_days=1, name="C")  # B と同じ開始 → B は全面置換
    client.post(f"{API}/plans/{c['planId']}/approve")
    assert client.get(f"{API}/plans/{b['planId']}").json()["status"] == "DISCARDED"

    cmp = client.get(f"{API}/plans/compare", params={"a": a["planId"], "b": c["planId"]}).json()
    assert cmp["a"]["planName"] == "A" and cmp["b"]["planName"] == "C"
    assert {k["key"] for k in cmp["kpis"]} >= {"late_orders", "setup_min"}
    assert cmp["changedCount"] == len(cmp["changes"])

    # 初日（10/27）は A の割付（置換日時より前）が配台表に出る
    d = client.get(f"{API}/dispatch", params={"siteId": site, "date": "2026-10-27"}).json()
    items = [i for r in d["resources"] for i in r["items"]]
    assert items and all(":" in i["start"] for i in items)

    draft = client.post(f"{API}/plans", json={
        "siteId": site, "horizonStart": c["horizonStart"], "horizonEnd": c["horizonEnd"], "planName": "D",
    }).json()
    assert client.post(f"{API}/plans/{draft['planId']}/discard").json()["status"] == "DISCARDED"
    copy = client.post(f"{API}/plans/{c['planId']}/copy", json={"planName": "C のコピー"}).json()
    assert copy["status"] == "DRAFT"
    assert len(client.get(f"{API}/plans/{copy['planId']}/assignments").json()) == 21


def test_sse_streams_until_finished(client, seeded, db_session, monkeypatch):
    from app.core import db as dbmod

    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=db_session.get_bind(), expire_on_commit=False))
    plan = solved_plan(client, seeded["siteId"])
    run_id = client.get(f"{API}/plans/{plan['planId']}/solver-runs").json()[0]["runId"]
    with client.stream("GET", f"{API}/solver-runs/{run_id}/events") as r:
        body = "".join(r.iter_text())
    assert body.startswith("data: ") and '"SUCCEEDED"' in body


def test_plan_create_accepts_site_local_time(client, seeded):
    # オフセットなし = 拠点の現地時刻（JST）→ UTC で保存
    plan = client.post(f"{API}/plans", json={
        "siteId": seeded["siteId"], "horizonStart": "2026-10-27T06:00:00", "horizonEnd": "2026-10-30T06:00:00",
    }).json()
    assert plan["horizonStart"] == "2026-10-26T21:00:00Z"
