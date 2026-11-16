"""実際のHTTP接続を開かず、FastAPIの受付処理へ直接リクエストするテスト用共通処理。"""
import json


# 実際のHTTP接続を開かず、FastAPIの受付処理へリクエストを渡す。
async def request(app, method, path, body=None):
    # リクエストとレスポンスの本文を保持する。
    payload = json.dumps(body).encode() if body is not None else b""
    messages = []

    # ASGIへ本文を1回だけ渡す受信処理。
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    # ASGIが返したステータスと本文を記録する送信処理。
    async def send(message):
        messages.append(message)

    # URLのパスと検索条件を分離する。
    route, _, query = path.partition("?")
    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
               "scheme": "http", "path": route, "raw_path": route.encode(), "query_string": query.replace("+", "%2B").encode(),
               "headers": [(b"content-type", b"application/json")], "server": ("test", 80), "client": ("test", 1),
               "root_path": ""}, receive, send)
    # 分割された本文をまとめ、APIの返却値を読み取る。
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(content) if content else None


