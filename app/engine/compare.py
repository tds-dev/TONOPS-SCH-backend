"""2 つの計画の比較（純粋関数）。

    kpi_deltas()       KPI ごとの A・B・差分と、B の方が良いか
    assignment_diff()  タスクごとの割付の違い（移動・設備変更・追加・削除）
"""
from dataclasses import dataclass
from datetime import datetime

# (表示名, 単位, 大きい方が良いか)
KPI_META: dict[str, tuple[str, str, bool]] = {
    "late_orders": ("納期遅れ", "件", False),
    "total_lateness_min": ("遅れ時間の合計", "分", False),
    "setup_min": ("段取り時間", "分", False),
    "makespan_min": ("最終オーダーの完了", "分", False),
    "utilisation_pct": ("平均負荷率", "%", True),
    "scheduled_tasks": ("割付済みタスク", "件", True),
    "unscheduled_tasks": ("未割付タスク", "件", False),
}


@dataclass
class KpiDelta:
    key: str
    label: str
    unit: str
    a: float | None
    b: float | None
    delta: float | None
    better: bool | None  # True = B が良い、False = B が悪い、None = 同じ・比較不可


def kpi_deltas(a: dict[str, float], b: dict[str, float]) -> list[KpiDelta]:
    out = []
    present = set(a) | set(b)
    for key in [k for k in KPI_META if k in present] + sorted(present - set(KPI_META)):
        label, unit, higher_better = KPI_META.get(key, (key, "", False))
        va, vb = a.get(key), b.get(key)
        delta = None if va is None or vb is None else round(vb - va, 4)
        better = None if not delta else (delta > 0) == higher_better
        out.append(KpiDelta(key, label, unit, va, vb, delta, better))
    return out


@dataclass
class Slot:
    resource_id: int
    start: datetime
    end: datetime


@dataclass
class SlotChange:
    task_id: int
    kind: str  # MOVED（時刻のみ）/ RESOURCE（設備変更）/ ADDED / REMOVED
    a: Slot | None
    b: Slot | None
    shift_minutes: int | None  # B の開始 − A の開始（正 = 後ろ倒し）


def assignment_diff(a: dict[int, Slot], b: dict[int, Slot]) -> list[SlotChange]:
    """タスクID → 割付 の 2 つの辞書を比較し、違いのあるタスクだけを返す。"""
    out = []
    for tid in sorted(set(a) | set(b)):
        sa, sb = a.get(tid), b.get(tid)
        if sa is None:
            out.append(SlotChange(tid, "ADDED", None, sb, None))
        elif sb is None:
            out.append(SlotChange(tid, "REMOVED", sa, None, None))
        elif sa.resource_id != sb.resource_id:
            out.append(SlotChange(tid, "RESOURCE", sa, sb, int((sb.start - sa.start).total_seconds() // 60)))
        elif sa.start != sb.start or sa.end != sb.end:
            out.append(SlotChange(tid, "MOVED", sa, sb, int((sb.start - sa.start).total_seconds() // 60)))
    out.sort(key=lambda c: (-abs(c.shift_minutes or 10**9), c.task_id))
    return out
