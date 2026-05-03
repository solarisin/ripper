"""Dashboard models package."""

# Import financial widgets to register them
from . import financial_widgets  # noqa: F401
from .dashboard import Dashboard, DashboardManager
from .data_source import DataSource, DataSourceType, DateRange, DateRangePreset
from .registry import WIDGET_REGISTRY, register_widget
from .widget_types import WidgetType
from .widgets import (
    BarChartWidget,
    BaseWidget,
    DataTableWidget,
    GaugeWidget,
    KPIWidget,
    LineChartWidget,
    PieChartWidget,
    WidgetConfig,
)

__all__ = [
    # Core classes
    "DataSource",
    "DataSourceType",
    "DateRange",
    "DateRangePreset",
    "Dashboard",
    "DashboardManager",
    # Widget system
    "BaseWidget",
    "WidgetConfig",
    "WidgetType",
    "register_widget",
    "WIDGET_REGISTRY",
    "financial_widgets",
    # Widget implementations
    "LineChartWidget",
    "BarChartWidget",
    "PieChartWidget",
    "DataTableWidget",
    "KPIWidget",
    "GaugeWidget",
]
