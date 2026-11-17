"""既存の英語KPIキーを、日本語の保存・API用キーへ揃える。"""
from typing import Any


# 既存DBの読込互換用。新しい集計結果には日本語キーを直接使用する。
LEGACY_KPI_KEYS = {
    "late_orders": "納期遅れ",
    "total_lateness_min": "遅れ時間の合計",
    "setup_min": "段取り時間",
    "makespan_min": "最終完了",
    "utilisation_pct": "平均負荷率",
    "scheduled_tasks": "割付済みタスク",
    "unscheduled_tasks": "未割付タスク",
}


# 移行前後の計画を同じキーで扱い、両方が存在する場合は日本語側の値を優先する。
def normalize_kpis(values: dict[str, Any]) -> dict[str, Any]:
    # 日本語キーと独自の指標はそのまま残し、旧キーだけを後から補う。
    normalized = {key: value for key, value in values.items() if key not in LEGACY_KPI_KEYS}
    for key, value in values.items():
        normalized.setdefault(LEGACY_KPI_KEYS.get(key, key), value)
    return normalized
