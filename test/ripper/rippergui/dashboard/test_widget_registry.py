"""Invariants for the dashboard widget registry and editor palette (#41).

These guard against re-introducing "dead" widget types: enum members with no
registered implementation, or palette entries that would let a user add a
non-functional widget.
"""

import pytest

from ripper.rippergui.dashboard.models import WIDGET_REGISTRY, WidgetType

# The four functional financial widgets are the only supported types.
FUNCTIONAL_TYPES = {
    WidgetType.SPENDING_TREND,
    WidgetType.CATEGORY_BREAKDOWN,
    WidgetType.BUDGET_VS_ACTUAL,
    WidgetType.TOP_EXPENSES,
}

# Value strings for the widget types removed in #41. None of these may reappear
# as WidgetType members or registry keys.
REMOVED_TYPE_VALUES = [
    "line_chart",
    "bar_chart",
    "pie_chart",
    "data_table",
    "kpi",
    "gauge",
    "net_worth",
    "savings_goal",
    "income_vs_expense",
]


def test_every_widget_type_has_a_registered_class():
    """No dangling enum type: importing the models package registers a class for each member."""
    unregistered = [wt for wt in WidgetType if wt not in WIDGET_REGISTRY]
    assert not unregistered, f"WidgetType members without a registered class: {unregistered}"


def test_registry_contains_exactly_the_functional_types():
    assert set(WIDGET_REGISTRY.keys()) == FUNCTIONAL_TYPES


def test_widget_type_enum_is_exactly_the_functional_types():
    assert set(WidgetType) == FUNCTIONAL_TYPES


def test_removed_types_are_not_valid_widget_types():
    for value in REMOVED_TYPE_VALUES:
        with pytest.raises(ValueError):
            WidgetType(value)


@pytest.mark.qt
def test_editor_palette_offers_only_functional_widget_types(qtbot):
    """The editor palette (WidgetList) must expose only functional widget types."""
    from PySide6.QtCore import Qt

    from ripper.rippergui.dashboard.models import Dashboard
    from ripper.rippergui.dashboard.views.dashboard_editor import DashboardEditor

    dashboard = Dashboard.create_new("Finance")
    editor = DashboardEditor(dashboard)
    qtbot.addWidget(editor)

    widget_list = editor.widget_palette.widget_list
    offered = {widget_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget_list.count())}
    assert offered == FUNCTIONAL_TYPES
