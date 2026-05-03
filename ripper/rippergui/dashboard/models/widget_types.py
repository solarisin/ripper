"""Widget type definitions."""

from enum import Enum


class WidgetType(Enum):
    """Types of dashboard widgets."""

    # Basic chart types
    LINE_CHART = "line_chart"
    BAR_CHART = "bar_chart"
    PIE_CHART = "pie_chart"
    DATA_TABLE = "data_table"
    KPI = "kpi"
    GAUGE = "gauge"

    # Financial-specific widgets
    SPENDING_TREND = "spending_trend"
    CATEGORY_BREAKDOWN = "category_breakdown"
    BUDGET_VS_ACTUAL = "budget_vs_actual"
    NET_WORTH = "net_worth"
    SAVINGS_GOAL = "savings_goal"
    TOP_EXPENSES = "top_expenses"
    INCOME_VS_EXPENSE = "income_vs_expense"
