"""すべてのモデルを import し、Base.metadata に全テーブルを登録する。"""
from app.models.masters import (  # noqa: F401
    AttributeDefinition,
    Calendar,
    CalendarException,
    ProductSwitchRule,
    ProductSwitchTime,
    Product,
    CalculationSetting,
    Resource,
    ResourceGroup,
    ProductProcess,
    ProductProcessResource,
    Rule,
    Location,
)
from app.models.transactions import (  # noqa: F401
    WorkActual,
    Order,
    Plan,
    PlanAssignment,
    PlanKpi,
    PlanViolation,
    SolverRun,
    Task,
    TaskDependency,
    TaskResourceOption,
)
