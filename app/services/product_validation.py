"""製品・製品工程・実行候補の入力と、所属拠点の整合性を確認する処理。"""
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import Location, ProcessGroup, Product, ProductProcess, Resource, ResourceGroup


# 部分更新では未送信の項目を元の保存値で補う。
def _value(original: Any, values: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in values:
        return values[key]
    if original is not None:
        return getattr(original, key)
    return default


# 名称の前後の空白を除き、必須と最大文字数を確認する。
def _name(original: Any, values: dict[str, Any], key: str, label: str) -> str:
    # 今回保存する名称。Noneを空文字へ変換して必須チェックを共通化する。
    name = str(_value(original, values, key) or "").strip()
    if not name or len(name) > 100:
        raise HTTPException(422, f"{label}は1～100文字で入力してください。")
    if key in values:
        values[key] = name
    return name


# 工程番号や分数に使用する整数の範囲を確認する。
def _integer(value: Any, label: str, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= 2147483647:
        raise HTTPException(422, f"{label}は{minimum}～2147483647の整数で入力してください。")


# 製品の名称・任意コード・所属拠点と、拠点内の名称重複を確認する。
def validate_product_write(db: Session, original: Product | None, values: dict[str, Any]) -> None:
    # 保存する名称と拠点。登録済み製品の所属を変えて既存オーダーと食い違うことを防ぐ。
    name = _name(original, values, "ProductName", "製品名")
    # コードの空欄はNULLへ揃え、NVARCHAR(100)を超える入力を保存前に拒否する。
    if "ProductCode" in values and values["ProductCode"] is not None:
        code = values["ProductCode"].strip()
        if len(code) > 100:
            raise HTTPException(422, "品目（製品）コードは100文字以内で入力してください。")
        values["ProductCode"] = code or None
    location_id = _value(original, values, "LocationID")
    if original is not None and location_id != original.LocationID:
        raise HTTPException(422, "登録済み製品の拠点は変更できません。")
    # 新しい製品を登録できる有効な拠点。
    location = db.get(Location, location_id) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    # 1日上限除外フラグは真偽値のみ許可する。
    exclude_cap = _value(original, values, "ExcludeFromDailyCap", False)
    if not isinstance(exclude_cap, bool):
        raise HTTPException(422, "日上限除外フラグはtrueまたはfalseで指定してください。")
    # 削除済みも含め、同じ拠点で製品名を重複させない。
    duplicate = db.scalar(select(Product.ProductID).where(Product.LocationID == location_id, Product.ProductName == name))
    if duplicate is not None and (original is None or duplicate != original.ProductID):
        raise HTTPException(409, "同じ拠点で製品名が登録済みです。別の名称を入力してください。")


# 製品工程の名称、順序、作業時間、待ち時間と製品参照を確認する。
def validate_product_process_write(db: Session, original: ProductProcess | None, values: dict[str, Any]) -> None:
    _name(original, values, "ProcessName", "工程名")
    # 製品の所属先は登録後に変更せず、既存タスクの生成元を保持する。
    product_id = _value(original, values, "ProductID")
    if original is not None and product_id != original.ProductID:
        raise HTTPException(422, "登録済み工程の製品は変更できません。")
    # 工程を登録する有効な製品。
    product = db.get(Product, product_id) if product_id is not None else None
    if product is None or product.DeleteFlag:
        raise HTTPException(422, "有効な製品を指定してください。")
    # 工程区分が指定された場合は、製品と同じ拠点の有効な工程区分であることを確認する。
    process_group_id = _value(original, values, "ProcessGroupID")
    if process_group_id is not None:
        group = db.get(ProcessGroup, process_group_id)
        if group is None or group.DeleteFlag or group.LocationID != product.LocationID:
            raise HTTPException(422, "製品と同じ拠点の有効な工程区分を指定してください。")
    # 工程番号と、この工程の後に必要な最小・最大待ち時間。
    sequence = _value(original, values, "SequenceNumber")
    minimum = _value(original, values, "MinLagAfterMin", 0)
    maximum = _value(original, values, "MaxLagAfterMin")
    _integer(sequence, "工程番号", 1)
    _integer(minimum, "最小待ち時間")
    if maximum is not None:
        _integer(maximum, "最大待ち時間")
        if maximum < minimum:
            raise HTTPException(422, "最大待ち時間は最小待ち時間以上にしてください。")
    # 日単位計算の「出荷日何日前を作業日目安とするか」・所要稼働日数・稼働日間隔を検証する。
    standard_offset = _value(original, values, "StandardOffsetDays")
    if standard_offset is not None:
        _integer(standard_offset, "出荷日何日前を作業日目安とするか")
    duration_days = _value(original, values, "DurationDays", 1)
    _integer(duration_days, "所要稼働日数", 1)
    min_lag_days = _value(original, values, "MinLagDays", 0)
    max_lag_days = _value(original, values, "MaxLagDays")
    _integer(min_lag_days, "次工程までの最小稼働日間隔")
    if max_lag_days is not None:
        _integer(max_lag_days, "次工程までの最大稼働日間隔")
        if max_lag_days < min_lag_days:
            raise HTTPException(422, "最大稼働日間隔は最小稼働日間隔以上にしてください。")
    # 終了直後の最大許容連休日数を検証する。NULLは制限なし。
    max_holidays_after = _value(original, values, "MaxHolidaysAfter")
    if max_holidays_after is not None:
        _integer(max_holidays_after, "次の工程を開始するまでに連続してもよい休日数（休日＋担当者年休）")
    # 工程番号の重複は専用保存処理で交換する。範囲は製品の工程数に合わせて確認する。
    validate_weekday_settings(original, values)
    validate_process_time(original, values)


# 曜日一覧・有効状態・日本時間の適用期間を確認し、部分更新でも既存値を保持する。
def validate_weekday_settings(original: ProductProcess | None, values: dict[str, Any]) -> None:
    # 設定がない新規工程は、全曜日を許可して既存の計算動作を維持する。
    weekdays = _value(original, values, "AllowedWeekdaysJSON", list(range(7)))
    if (not isinstance(weekdays, list) or not weekdays
            or any(type(day) is not int or not 0 <= day <= 6 for day in weekdays)
            or len(set(weekdays)) != len(weekdays)):
        raise HTTPException(422, "許可曜日は0（日曜）～6（土曜）の重複しない整数を1つ以上指定してください。")
    # 画面以外からの登録も曜日番号順に揃え、取得時の表示と差分を安定させる。
    if "AllowedWeekdaysJSON" in values:
        values["AllowedWeekdaysJSON"] = sorted(weekdays)
    # nullを有効状態として保存せず、明示した真偽値だけを受け付ける。
    enabled = _value(original, values, "WeekdayRestrictionEnabled", True)
    if not isinstance(enabled, bool):
        raise HTTPException(422, "曜日制限の有効状態はtrueまたはfalseで指定してください。")
    # API側で日本時間へ変換された日時を、そのまま前後比較する。
    start = _value(original, values, "WeekdayRestrictionStartAt")
    end = _value(original, values, "WeekdayRestrictionEndAt")
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "曜日制限の終了日時は開始日時以降にしてください。")


# 工程の実行候補を同じ拠点に限定し、設備かグループの片方を確認する。
def validate_product_process_resource_write(db: Session, original: Any, values: dict[str, Any]) -> None:
    # この候補が属する工程と製品。
    process_id = _value(original, values, "ProductProcessID")
    if original is not None and process_id != original.ProductProcessID:
        raise HTTPException(422, "登録済み実行候補の工程は変更できません。")
    process = db.get(ProductProcess, process_id) if process_id is not None else None
    product = db.get(Product, process.ProductID) if process is not None else None
    if product is None or product.DeleteFlag:
        raise HTTPException(422, "有効な製品工程を指定してください。")
    # 設備とグループは排他的に指定し、製品と同じ拠点の有効な候補だけを許可する。
    resource_id = _value(original, values, "ResourceID")
    group_id = _value(original, values, "ResourceGroupID")
    if (resource_id is None) == (group_id is None):
        raise HTTPException(422, "リソースかグループのどちらか一方だけを指定してください。")
    target = db.get(Resource, resource_id) if resource_id is not None else db.get(ResourceGroup, group_id)
    if target is None or target.DeleteFlag or target.LocationID != product.LocationID:
        raise HTTPException(422, "製品と同じ拠点の有効なリソースかグループを指定してください。")


# 設備候補の有無に関係なく、工程共通の作業時間の範囲と精度を確認する。
def validate_process_time(original: ProductProcess | None, values: dict[str, Any]) -> None:
    # 準備・固定は未指定ならNULL、指定時は整数分。作業時間は小数4桁まで。
    setup = _value(original, values, "SetupMinutes")
    fixed = _value(original, values, "FixedMinutes")
    processing = _value(original, values, "ProcessingMinutes", 0)
    if setup is not None:
        _integer(setup, "準備時間")
    if fixed is not None:
        _integer(fixed, "固定時間")
    # 浮動小数の丸め誤差を避けてDBのNUMERIC(12,4)の範囲と桁数を確認する。
    decimal_processing = Decimal(str(processing)) if processing is not None else None
    if (decimal_processing is None or not decimal_processing.is_finite()
            or decimal_processing < 0 or decimal_processing > Decimal("99999999.9999")
            or decimal_processing != decimal_processing.quantize(Decimal("0.0001"))):
        raise HTTPException(422, "作業時間は0以上99999999.9999以下、小数点以下4桁以内で入力してください。")
    # 日単位計算では標準時間未確定（0分）の工程を扱うため、保存時の0超必須チェックは行わない。
