"""Rule plugin registry.

A rule plugin adds constraints (or penalties) to the CP-SAT model and can
check a finished schedule. Customer-specific rules live in their own modules
and register themselves with @register; nothing in the core engine changes.

    @register
    class MyRule(RulePlugin):
        type_key = "my_rule"
        label = "表示名"
        def apply(self, ctx, rule): ...      # add constraints via ctx.model
        def check(self, problem, rule, assignments): ...  # return Violations

This module must not import OR-Tools: `check` is used by pure code paths.
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
    params_schema: ClassVar[dict[str, Any]] = {"type": "object"}  # JSON Schema for the UI form

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


# Built-in plugins register themselves on import.
from app.engine.rules import allowed_weekdays  # noqa: E402,F401
