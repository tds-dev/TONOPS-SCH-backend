"""既存SQL Serverの曜日制限を製品工程へ移し、旧属性定義・ルールを廃止する移行処理。"""
import argparse
import json
from datetime import date, datetime, time

from sqlalchemy import MetaData, Table, inspect, select, text


# JSON列を反映した旧テーブルは文字列型になるため、既存の値をPythonへ復元する。
def read_json(value, default):
    return json.loads(value) if isinstance(value, str) else default if value is None else value


# 廃止前の対象条件を移行時だけ照合し、不明な演算子は黙って無視しない。
def legacy_matches(selector: dict, attrs: dict) -> bool:
    for key, condition in selector.items():
        # 対象作業が持つ属性値。通常の計算処理ではこの判定を使用しない。
        value = attrs.get(key)
        if not isinstance(condition, dict):
            if value != condition:
                return False
            continue
        if not condition or set(condition) - {"eq", "ne", "in", "notIn"}:
            raise ValueError("旧ルールに移行できない対象条件がある。")
        for operator, expected in condition.items():
            if operator in {"in", "notIn"} and not isinstance(expected, list):
                raise ValueError("旧ルールのin・notInには一覧が必要。")
            if ((operator == "eq" and value != expected) or (operator == "ne" and value == expected)
                    or (operator == "in" and value not in expected)
                    or (operator == "notIn" and value in expected)):
                return False
    return True


# 従来の日付単位の有効期間を、日本時間の日初・日末の日時へ変換する。
def period_datetime(value, end: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if isinstance(value, datetime):
        value = value.date()
    return datetime.combine(value, time.max if end else time.min)


# 既存作業の属性を使い、各工程へ一意に移せる曜日設定だけを組み立てる。
def plan_restrictions(rules: list[dict], processes: list[dict], tasks: list[dict]) -> dict[int, dict]:
    # 同じ工程に属する全作業を比較し、作業ごとの条件差を失わないようにする。
    tasks_by_process = {}
    for task in tasks:
        tasks_by_process.setdefault(task["ProductProcessID"], []).append(read_json(task.get("AttributesJSON"), {}))
    result = {}
    for rule in rules:
        if rule["RuleTypeKey"] != "allowed_weekdays":
            raise ValueError(f"ルール{rule['RuleID']}: 未対応の種類を確認してから移行する必要がある。")
        if not rule.get("IsHard", True):
            raise ValueError(f"ルール{rule['RuleID']}: 工程の曜日制限へ移す前に、必須条件への統一を確認する必要がある。")
        # 旧ルールの設定値。曜日以外の設定も、削除前に明示的に検出する。
        selector = read_json(rule["SelectorJSON"], {})
        params = read_json(rule["ParamsJSON"], {})
        weekdays = params.get("weekdays") if isinstance(params, dict) else None
        if (not isinstance(selector, dict) or not isinstance(params, dict) or set(params) != {"weekdays"} or not isinstance(weekdays, list)
                or not weekdays or any(type(day) is not int or not 0 <= day <= 6 for day in weekdays)
                or len(set(weekdays)) != len(weekdays)):
            raise ValueError(f"ルール{rule['RuleID']}: 対象条件または許可曜日が不正。")
        # 一つの工程行に移す適用期間。旧仕様どおり終了日も含める。
        setting = {"AllowedWeekdaysJSON": sorted(weekdays), "WeekdayRestrictionEnabled": bool(rule["IsActive"]),
                   "WeekdayRestrictionStartAt": period_datetime(rule.get("ValidFrom")),
                   "WeekdayRestrictionEndAt": period_datetime(rule.get("ValidTo"), end=True)}
        if (setting["WeekdayRestrictionStartAt"] is not None and setting["WeekdayRestrictionEndAt"] is not None
                and setting["WeekdayRestrictionStartAt"] > setting["WeekdayRestrictionEndAt"]):
            raise ValueError(f"ルール{rule['RuleID']}: 有効期間が逆転している。")
        matched = []
        for process in processes:
            if process["LocationID"] != rule["LocationID"]:
                continue
            process_id = process["ProductProcessID"]
            attributes = tasks_by_process.get(process_id, [])
            if selector and not attributes:
                raise ValueError(f"工程{process_id}: 対象条件を判定できる作業がないため、移行先を確認する必要がある。")
            flags = [legacy_matches(selector, attrs) for attrs in attributes] if selector else [True]
            if any(flags) and not all(flags):
                raise ValueError(f"工程{process_id}: 作業ごとに対象条件が異なるため、工程への集約を確認する必要がある。")
            if not any(flags):
                continue
            matched.append(process_id)
            existing = result.get(process_id)
            if existing is not None:
                # 同じ適用期間の必須ルールだけは、許可曜日の共通部分へまとめられる。
                if any(existing[key] != setting[key] for key in setting if key != "AllowedWeekdaysJSON"):
                    raise ValueError(f"工程{process_id}: 複数の期間・有効状態を1行へ集約できない。")
                setting = {**setting, "AllowedWeekdaysJSON": sorted(set(existing["AllowedWeekdaysJSON"]) & set(weekdays))}
                if not setting["AllowedWeekdaysJSON"]:
                    raise ValueError(f"工程{process_id}: 許可曜日の共通部分がない。")
            result[process_id] = setting.copy()
        if not matched:
            raise ValueError(f"ルール{rule['RuleID']}: 対象工程がないため、削除前に移行先を確認する必要がある。")
    return result


# 通常モデルを読み込まず、旧テーブルを含む実際のDB定義から移行内容を取得する。
def inspect_migration(connection) -> dict[int, dict]:
    # 移行済みの場合は再実行しても新しい工程設定を書き換えない。
    inspector = inspect(connection)
    if not inspector.has_table("M_Rules"):
        return {}
    metadata = MetaData()
    rules = Table("M_Rules", metadata, autoload_with=connection)
    processes = Table("M_ProductProcesses", metadata, autoload_with=connection)
    products = Table("M_Product", metadata, autoload_with=connection)
    tasks = Table("T_Tasks", metadata, autoload_with=connection)
    orders = Table("T_Orders", metadata, autoload_with=connection)
    # 別製品の工程へ誤って紐づいた作業を、移行判断へ混入させない。
    task_rows = connection.execute(select(tasks).join(orders, tasks.c.OrderID == orders.c.OrderID)
                                   .join(processes, tasks.c.ProductProcessID == processes.c.ProductProcessID)
                                   .where(orders.c.ProductID == processes.c.ProductID)).mappings().all()
    process_rows = connection.execute(select(processes.c.ProductProcessID, products.c.LocationID)
                                      .join(products, processes.c.ProductID == products.c.ProductID)).mappings().all()
    return plan_restrictions(list(connection.execute(select(rules)).mappings()), list(process_rows), list(task_rows))


# 一つのトランザクションで設定移行・外部キー解除・旧2テーブル削除を行う。
def apply_migration(connection, settings: dict[int, dict]) -> None:
    if connection.dialect.name != "mssql":
        raise ValueError("実DBの構造変更はSQL Serverだけに対応する。")
    # 実行直前にも設定を読み直し、確認後に旧ルールが変わっていないことを確認する。
    if inspect_migration(connection) != settings:
        raise ValueError("確認後に旧ルールまたは対象作業が変わったため、再確認が必要。")
    columns = {col["name"] for col in inspect(connection).get_columns("M_ProductProcesses")}
    definitions = {
        "AllowedWeekdaysJSON": "NVARCHAR(MAX) NOT NULL CONSTRAINT DF_M_ProductProcesses_AllowedWeekdaysJSON DEFAULT N'[0,1,2,3,4,5,6]' WITH VALUES",
        "WeekdayRestrictionEnabled": "BIT NOT NULL CONSTRAINT DF_M_ProductProcesses_WeekdayRestrictionEnabled DEFAULT 1 WITH VALUES",
        "WeekdayRestrictionStartAt": "DATETIME2(7) NULL",
        "WeekdayRestrictionEndAt": "DATETIME2(7) NULL",
    }
    for name, definition in definitions.items():
        if name not in columns:
            connection.execute(text(f"ALTER TABLE [M_ProductProcesses] ADD [{name}] {definition}"))
    for process_id, setting in settings.items():
        # 列追加だけを先に行って設定済みの場合も、確認なしに既存値を上書きしない。
        current = connection.execute(text("SELECT [AllowedWeekdaysJSON], [WeekdayRestrictionEnabled], "
                                          "[WeekdayRestrictionStartAt], [WeekdayRestrictionEndAt] "
                                          "FROM [M_ProductProcesses] WHERE [ProductProcessID]=:process_id"),
                                     {"process_id": process_id}).mappings().one()
        saved = {**dict(current), "AllowedWeekdaysJSON": read_json(current["AllowedWeekdaysJSON"], [])}
        default = {"AllowedWeekdaysJSON": list(range(7)), "WeekdayRestrictionEnabled": True,
                   "WeekdayRestrictionStartAt": None, "WeekdayRestrictionEndAt": None}
        if saved != default and saved != setting:
            raise ValueError(f"工程{process_id}: 新カラムへ設定済みの内容と旧ルールが異なる。")
        # 既存の工程ID・タスクID・割付・実績は変更せず、曜日設定だけを保存する。
        values = {**setting, "AllowedWeekdaysJSON": json.dumps(setting["AllowedWeekdaysJSON"]), "process_id": process_id}
        connection.execute(text("UPDATE [M_ProductProcesses] SET [AllowedWeekdaysJSON]=:AllowedWeekdaysJSON, "
                                "[WeekdayRestrictionEnabled]=:WeekdayRestrictionEnabled, "
                                "[WeekdayRestrictionStartAt]=:WeekdayRestrictionStartAt, "
                                "[WeekdayRestrictionEndAt]=:WeekdayRestrictionEndAt WHERE [ProductProcessID]=:process_id"), values)
    # 新規作成SQLと同じ、適用期間の前後関係チェックを追加する。
    connection.execute(text("IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name=N'CK_M_ProductProcesses_WeekdayRestrictionPeriod') "
                            "ALTER TABLE [M_ProductProcesses] ADD CONSTRAINT [CK_M_ProductProcesses_WeekdayRestrictionPeriod] "
                            "CHECK (WeekdayRestrictionStartAt IS NULL OR WeekdayRestrictionEndAt IS NULL OR WeekdayRestrictionStartAt <= WeekdayRestrictionEndAt)"))
    # 旧ルールを参照する外部キーだけを先に外し、違反行とメッセージを保持する。
    inspector = inspect(connection)
    for fk in inspector.get_foreign_keys("T_PlanViolations"):
        if "RuleID" in fk["constrained_columns"]:
            name = connection.dialect.identifier_preparer.quote(fk["name"])
            connection.execute(text(f"ALTER TABLE [T_PlanViolations] DROP CONSTRAINT {name}"))
    if any(col["name"] == "RuleID" for col in inspector.get_columns("T_PlanViolations")):
        connection.execute(text("ALTER TABLE [T_PlanViolations] DROP COLUMN [RuleID]"))
    for table in ["M_Rules", "M_AttributeDefinitions"]:
        connection.execute(text(f"IF OBJECT_ID(N'dbo.{table}', N'U') IS NOT NULL DROP TABLE [{table}]"))


# 既定では移行予定だけを表示し、--apply指定時に同一トランザクション内で更新する。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="検証後にDB更新を実行する")
    args = parser.parse_args()
    # 実行時だけ設定を読み込み、関数利用やヘルプ表示では実DBへ接続しない。
    from app.core.db import engine
    with engine.begin() as connection:
        # アプリ停止中に実行し、移行対象の旧ルールと作業の同時更新を避ける。
        if args.apply and connection.dialect.name == "mssql":
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        settings = inspect_migration(connection)
        print(f"曜日設定の移行対象: {len(settings)}工程")
        for process_id, setting in settings.items():
            print(process_id, json.dumps(setting, ensure_ascii=False, default=str))
        if args.apply:
            apply_migration(connection, settings)
        else:
            print("確認のみ。更新する場合はアプリ停止後に--applyを指定する。")
    # コミットが完了してから、更新完了を通知する。
    if args.apply:
        print("工程カラムの追加と旧2テーブルの廃止が完了。")


if __name__ == "__main__":
    main()
