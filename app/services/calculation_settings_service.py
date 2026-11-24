"""計算設定の入力を検証し、拠点ごとの既定設定を切り替える。"""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import CalculationSetting, Location, TIME_UNITS


# 部分更新を既存値と合わせて検証し、他設定の既定解除も同じ保存処理で行う。
def save_calculation_setting(
    db: Session, original: CalculationSetting | None, values: dict[str, Any], user: str,
) -> CalculationSetting:
    # 未送信の項目は既存値またはモデルと同じ初期値で補う。
    current = {
        key: getattr(original, key) if original is not None else default
        for key, default in {
            "LocationID": None, "CalculationSettingName": None, "TimeUnit": "DAY",
            "ObjectiveWeightsJSON": {}, "FrozenWindowHours": 0, "IsDefault": False,
        }.items()
    }
    current.update(values)
    if original is not None and current["LocationID"] != original.LocationID:
        raise HTTPException(422, "登録済み計算設定の拠点は変更できません。")
    # SQL Serverでは同じ拠点の保存を直列化し、既定設定の同時登録を防ぐ。
    location = db.scalar(
        select(Location).where(Location.LocationID == current["LocationID"])
        .with_hint(Location, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
    )
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    name = current["CalculationSettingName"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise HTTPException(422, "設定名は1～100文字で入力してください。")
    if current["TimeUnit"] not in TIME_UNITS:
        raise HTTPException(422, "時間単位はMINUTEまたはDAYを指定してください。")
    # 負数やnullを計算へ渡さず、DBの整数列に収まる値だけを保存する。
    hours = current["FrozenWindowHours"]
    if type(hours) is not int or not 0 <= hours <= 2147483647:
        raise HTTPException(422, "固定期間は0～2147483647の整数で入力してください。")
    weights = current["ObjectiveWeightsJSON"]
    if not isinstance(weights, dict) or any(
        type(weight) is not int or not 0 <= weight <= 2147483647 for weight in weights.values()
    ):
        raise HTTPException(422, "評価の重みは項目名と0～2147483647の整数の組合せで指定してください。")
    if type(current["IsDefault"]) is not bool:
        raise HTTPException(422, "既定設定はtrueまたはfalseで指定してください。")
    # 同じ名称の選択肢を作らず、計画作成時に設定を識別できるようにする。
    duplicate = db.scalar(select(CalculationSetting.CalculationSettingID).where(
        CalculationSetting.LocationID == location.LocationID,
        CalculationSetting.CalculationSettingName == name.strip(),
    ))
    if duplicate is not None and (original is None or duplicate != original.CalculationSettingID):
        raise HTTPException(409, "同じ拠点で設定名が登録済みです。別の名称を入力してください。")
    if current["IsDefault"]:
        for setting in db.scalars(select(CalculationSetting).where(
            CalculationSetting.LocationID == location.LocationID, CalculationSetting.IsDefault.is_(True),
        )):
            if original is None or setting.CalculationSettingID != original.CalculationSettingID:
                setting.IsDefault = False
                setting.UpdatedBy = user
    # APIの既存形式を維持し、送られた項目だけを更新する。
    values["CalculationSettingName"] = name.strip()
    if original is None:
        original = CalculationSetting(**values, CreatedBy=user)
        db.add(original)
    else:
        for key, value in values.items():
            setattr(original, key, value)
        original.UpdatedBy = user
    return original
