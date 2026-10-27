"""ルールプラグインのレジストリ。

ルールプラグインは CP-SAT モデルに制約（またはペナルティ）を追加し、完成した
スケジュールを検証できる。顧客固有のルールは独自モジュールに置き、@register で
登録する。コアエンジンは変更しない。

    @register
    class MyRule(RulePlugin):
        type_key = "my_rule"
        label = "表示名"
        def apply(self, ctx, rule): ...      # ctx.model に制約を追加
        def check(self, problem, rule, assignments): ...  # Violation のリストを返す

このモジュールは OR-Tools を import してはならない（`check` は純粋な処理から使う）。
"""
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from app.engine.model_builder import BuildContext
    from app.engine.problem import Problem, PRule
    from app.engine.result import SAssignment, Violation

_REGISTRY: dict[str, "RulePlugin"] = {}


class RulePlugin:
    type_key: ClassVar[str] = ""
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""
    supports_soft: ClassVar[bool] = False
    params_schema: ClassVar[dict[str, Any]] = {"type": "object"}  # 画面のフォーム用 JSON Schema

    def apply(self, ctx: "BuildContext", rule: "PRule") -> None:
        raise NotImplementedError

    def check(self, problem: "Problem", rule: "PRule", assignments: list["SAssignment"]) -> list["Violation"]:
        return []


def register(cls: type[RulePlugin]) -> type[RulePlugin]:
    _REGISTRY[cls.type_key] = cls()
    return cls


def get_plugin(type_key: str) -> RulePlugin | None:
    return _REGISTRY.get(type_key)


def all_plugins() -> list[RulePlugin]:
    return list(_REGISTRY.values())


# 組込みプラグインは import 時に自身を登録する。
from app.engine.rules import allowed_weekdays  # noqa: E402,F401
