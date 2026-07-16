"""Widget type definitions."""

from enum import Enum


class WidgetType(Enum):
    """Types of dashboard widgets."""

    # Financial-specific widgets
    SPENDING_TREND = "spending_trend"
    CATEGORY_BREAKDOWN = "category_breakdown"
    BUDGET_VS_ACTUAL = "budget_vs_actual"
    TOP_EXPENSES = "top_expenses"
