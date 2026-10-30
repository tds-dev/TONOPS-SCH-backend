"""フェーズ1: マスタの CRUD、タスク生成、稼働時間。"""


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_resource_crud_camel_case_and_soft_delete(client, seeded):
    site_id = seeded["siteId"]
    groups = client.get("/api/v1/resource-groups", params={"siteId": site_id}).json()
    assert [g["groupCode"] for g in groups] == ["MIX", "FIL", "PAC"]

    body = {
        "siteId": site_id,
        "resourceGroupId": groups[0]["resourceGroupId"],
        "resourceCode": "M-03",
        "resourceName": "配合機 M-03",
        "capacity": 1,
    }
    r = client.post("/api/v1/resources", json=body, headers={"X-User-Email": "test@example.com"})
    assert r.status_code == 201, r.text
    res = r.json()
    assert res["resourceType"] == "MACHINE"  # 既定値が適用される
    assert res["createdBy"] == "test@example.com"

    r = client.patch(f"/api/v1/resources/{res['resourceId']}", json={"resourceName": "配合機 3号"})
    assert r.json()["resourceName"] == "配合機 3号"

    # 同一拠点でコード重複 -> 409
    assert client.post("/api/v1/resources", json=body).status_code == 409

    assert client.delete(f"/api/v1/resources/{res['resourceId']}").status_code == 204
    codes = [x["resourceCode"] for x in client.get("/api/v1/resources", params={"siteId": site_id}).json()]
    assert "M-03" not in codes and len(codes) == 6
    all_codes = client.get("/api/v1/resources", params={"siteId": site_id, "includeDeleted": "true"}).json()
    assert len(all_codes) == 7


def test_generated_tasks_options_and_dependencies(client, seeded):
    orders = client.get("/api/v1/orders", params={"siteId": seeded["siteId"]}).json()
    order = next(j for j in orders if j["orderNo"] == "JB-1041")  # A-200 を 1,200 kg
    tasks = client.get(f"/api/v1/orders/{order['orderId']}/tasks").json()
    assert [t["taskName"] for t in tasks] == ["配合", "充填", "包装"]
    assert tasks[0]["attributesJSON"] == {"family": "A"}
    # 配合: 段取り 0 + 1200 × 0.12 = 144 分、充填: 15 + 120 = 135、包装: 10 + 96 = 106
    assert [t["options"][0]["durationMin"] for t in tasks] == [144, 135, 106]
    deps = client.get(f"/api/v1/orders/{order['orderId']}/dependencies").json()
    assert [(d["dependencyType"], d["lagMin"]) for d in deps] == [("FS", 60), ("FS", 0)]

    # replace なしの再生成は拒否、replace ありなら作り直す
    assert client.post(f"/api/v1/orders/{order['orderId']}/generate-tasks").status_code == 409
    r = client.post(f"/api/v1/orders/{order['orderId']}/generate-tasks", params={"replace": "true"})
    assert r.status_code == 200 and len(r.json()) == 3


def test_calendar_working_time_endpoint(client, seeded):
    cal = client.get("/api/v1/calendars", params={"siteId": seeded["siteId"]}).json()[0]
    r = client.get(
        f"/api/v1/calendars/{cal['calendarId']}/working-time",
        params={"from": "2026-10-27T00:00:00+09:00", "to": "2026-10-28T00:00:00+09:00"},
    )
    assert r.status_code == 200
    assert r.json() == [
        {"start": "2026-10-26T21:00:00Z", "end": "2026-10-27T03:00:00Z"},
        {"start": "2026-10-27T04:00:00Z", "end": "2026-10-27T13:00:00Z"},
    ]
