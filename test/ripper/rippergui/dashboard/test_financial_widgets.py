"""Tests for financial dashboard models."""

import warnings
from datetime import datetime

import pytest
from PySide6.QtCharts import QBarCategoryAxis
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from ripper.rippergui.dashboard.models.dashboard import Dashboard
from ripper.rippergui.dashboard.models.data_source import DataSource, DataSourceType, DateRange, DateRangePreset
from ripper.rippergui.dashboard.models.financial_widgets import (
    BudgetVsActualWidget,
    CategoryBreakdownWidget,
    SpendingTrendWidget,
    TopExpensesWidget,
)
from ripper.rippergui.dashboard.models.tiller_data import TillerDataProcessor
from ripper.rippergui.dashboard.models.widget_types import WidgetType
from ripper.rippergui.dashboard.models.widgets import WidgetConfig


def _assert_no_deprecated_axis_api(recorded_warnings) -> None:
    """Fail if any deprecated Qt5-era QChart axis call was made."""
    offenders = [
        str(warning.message)
        for warning in recorded_warnings
        if issubclass(warning.category, DeprecationWarning)
        and any(token in str(warning.message) for token in ("QChart.axisX", "QChart.axisY", "QChart.setAxisX"))
    ]
    assert not offenders, f"deprecated QChart axis API used: {offenders}"


@pytest.fixture
def sample_dashboard():
    """Create a sample dashboard for testing."""
    dashboard = Dashboard(
        id="test_dashboard_1",
        name="Test Dashboard",
        description="Test dashboard for financial widgets",
        grid_size=(12, 12),
        version="1.0",
    )
    return dashboard


@pytest.fixture
def sample_widget_config():
    """Create a sample widget configuration."""
    return WidgetConfig(
        id="test_widget_1",
        type=WidgetType.SPENDING_TREND,
        title="Test Spending Trend",
        position=(0, 0),
        size=(4, 3),
        data_source_id="test_source",
    )


@pytest.mark.qt
class TestSpendingTrendWidget:
    """Test cases for SpendingTrendWidget."""

    def test_widget_initialization(self, sample_widget_config, sample_dashboard, qtbot):
        """Test that the widget initializes correctly."""
        widget = SpendingTrendWidget(sample_widget_config, sample_dashboard)
        assert widget.config == sample_widget_config
        assert widget.dashboard == sample_dashboard
        assert widget.chart_view is None
        assert widget.data_processor is None

    def test_create_widget(self, sample_widget_config, sample_dashboard, qtbot):
        """Test that the widget creates correctly."""
        widget = SpendingTrendWidget(sample_widget_config, sample_dashboard)

        parent = QWidget()
        qtbot.addWidget(parent)

        created_widget = widget.create_widget(parent)
        assert created_widget is not None
        assert created_widget.parent() == parent
        assert widget.chart_view is not None

    def test_update_data_no_data_source(self, sample_widget_config, sample_dashboard, qtbot):
        """Test update_data when there's no data source."""
        config_no_source = WidgetConfig(
            id="test_widget_no_source",
            type=WidgetType.SPENDING_TREND,
            title="Test Spending Trend No Source",
            position=(0, 0),
            size=(4, 3),
            data_source_id=None,
        )
        widget = SpendingTrendWidget(config_no_source, sample_dashboard)

        # Should not raise an exception
        widget.update_data()

    def test_update_chart_attaches_titled_axes(self, sample_widget_config, sample_dashboard, qtbot):
        """_update_chart should attach axes via the Qt6 API with the expected titles."""
        widget = SpendingTrendWidget(sample_widget_config, sample_dashboard)
        parent = QWidget()
        qtbot.addWidget(parent)
        widget.create_widget(parent)

        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            widget._update_chart(
                [
                    {"month": "2026-01", "amount": -100.0},
                    {"month": "2026-02", "amount": -250.0},
                ]
            )
        _assert_no_deprecated_axis_api(recorded)

        assert widget.chart_view is not None
        chart = widget.chart_view.chart()

        horizontal_axes = chart.axes(Qt.Orientation.Horizontal)
        vertical_axes = chart.axes(Qt.Orientation.Vertical)
        assert horizontal_axes, "expected a horizontal axis to be attached"
        assert vertical_axes, "expected a vertical axis to be attached"
        assert horizontal_axes[0].titleText() == "Month"
        assert vertical_axes[0].titleText() == "Amount ($)"

        # Axes must be attached to the series (Qt6 addAxis/attachAxis semantics).
        series = chart.series()[0]
        assert horizontal_axes[0] in series.attachedAxes()
        assert vertical_axes[0] in series.attachedAxes()


@pytest.mark.qt
class TestCategoryBreakdownWidget:
    """Test cases for CategoryBreakdownWidget."""

    def test_widget_initialization(self, sample_widget_config, sample_dashboard, qtbot):
        """Test that the widget initializes correctly."""
        widget = CategoryBreakdownWidget(sample_widget_config, sample_dashboard)
        assert widget.config == sample_widget_config
        assert widget.dashboard == sample_dashboard
        assert widget.chart_view is None
        assert widget.data_processor is None
        assert widget.min_percentage == 2.0

    def test_create_widget(self, sample_widget_config, sample_dashboard, qtbot):
        """Test that the widget creates correctly."""
        widget = CategoryBreakdownWidget(sample_widget_config, sample_dashboard)

        parent = QWidget()
        qtbot.addWidget(parent)

        created_widget = widget.create_widget(parent)
        assert created_widget is not None
        assert created_widget.parent() == parent
        assert widget.chart_view is not None


@pytest.mark.qt
class TestBudgetVsActualWidget:
    """Test cases for BudgetVsActualWidget."""

    def test_widget_initialization(self, sample_widget_config, sample_dashboard, qtbot):
        """Test that the widget initializes correctly."""
        widget = BudgetVsActualWidget(sample_widget_config, sample_dashboard)
        assert widget.config == sample_widget_config
        assert widget.dashboard == sample_dashboard
        assert widget.chart_view is None
        assert widget.data_processor is None
        assert isinstance(widget.budget_data, dict)

    def test_create_widget(self, sample_widget_config, sample_dashboard, qtbot):
        """Test that the widget creates correctly."""
        widget = BudgetVsActualWidget(sample_widget_config, sample_dashboard)

        parent = QWidget()
        qtbot.addWidget(parent)

        created_widget = widget.create_widget(parent)
        assert created_widget is not None
        assert created_widget.parent() == parent
        assert widget.chart_view is not None

    def test_update_chart_attaches_category_and_value_axes(self, sample_widget_config, sample_dashboard, qtbot):
        """_update_chart should attach a category X axis and titled value Y axis (Qt6 API)."""
        widget = BudgetVsActualWidget(sample_widget_config, sample_dashboard)
        parent = QWidget()
        qtbot.addWidget(parent)
        widget.create_widget(parent)

        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            widget._update_chart(
                [
                    {"category": "Food", "budgeted": 400.0, "amount": -350.0},
                    {"category": "Housing", "budgeted": 1500.0, "amount": -1500.0},
                ]
            )
        _assert_no_deprecated_axis_api(recorded)

        assert widget.chart_view is not None
        chart = widget.chart_view.chart()

        horizontal_axes = chart.axes(Qt.Orientation.Horizontal)
        vertical_axes = chart.axes(Qt.Orientation.Vertical)
        assert horizontal_axes, "expected a horizontal axis to be attached"
        assert vertical_axes, "expected a vertical axis to be attached"
        assert isinstance(horizontal_axes[0], QBarCategoryAxis)
        assert list(horizontal_axes[0].categories()) == ["Food", "Housing"]
        assert horizontal_axes[0].titleText() == "Category"
        assert vertical_axes[0].titleText() == "Amount ($)"

        series = chart.series()[0]
        assert horizontal_axes[0] in series.attachedAxes()
        assert vertical_axes[0] in series.attachedAxes()


@pytest.mark.qt
class TestTopExpensesWidget:
    """Test cases for TopExpensesWidget."""

    def test_update_data_formats_currency_amounts_without_nan(self, sample_dashboard, qtbot):
        """Test that formatted currency and blank amount rows do not render as $nan."""
        data_source = DataSource(
            id="test_source",
            type=DataSourceType.TILLER_TRANSACTIONS,
            name="Transactions",
            spreadsheet_id="spreadsheet",
            sheet_name="Transactions",
            range_a1="A:E",
            date_range=DateRange(
                DateRangePreset.CUSTOM,
                start_date=datetime(2026, 1, 1),
                end_date=datetime(2026, 12, 31, 23, 59, 59),
            ),
        )
        sample_dashboard.add_data_source(data_source)
        config = WidgetConfig(
            id="top_expenses",
            type=WidgetType.TOP_EXPENSES,
            title="Top Expenses",
            position=(0, 0),
            size=(4, 3),
            data_source_id=data_source.id,
        )
        widget = TopExpensesWidget(config, sample_dashboard)

        parent = QWidget()
        qtbot.addWidget(parent)
        widget.create_widget(parent)
        widget.update_data(
            {
                data_source.id: [
                    {
                        "date": "2026-04-15",
                        "description": "Groceries",
                        "category": "Food",
                        "amount": "$1,234.56",
                        "account": "Checking",
                    },
                    {
                        "date": "2026-04-16",
                        "description": "Bad empty row",
                        "category": "Unknown",
                        "amount": "",
                        "account": "Checking",
                    },
                    {
                        "date": "2026-04-17",
                        "description": "Refund",
                        "category": "Food",
                        "amount": "25.00",
                        "account": "Checking",
                    },
                    {
                        "date": "2026-04-18",
                        "description": "Rent",
                        "category": "Housing",
                        "amount": "-1500",
                        "account": "Checking",
                    },
                ]
            }
        )

        assert widget.table is not None
        rendered_amounts = [widget.table.item(row, 3).text() for row in range(widget.table.rowCount())]
        assert "$nan" not in rendered_amounts
        assert "$1,500.00" in rendered_amounts


class TestTillerDataProcessor:
    """Test cases for TillerDataProcessor."""

    def test_get_top_expenses_parses_formatted_amounts_and_drops_invalid_values(self):
        """Test that top expenses do not include NaN amounts."""
        processor = TillerDataProcessor(
            [
                {"date": "2026-04-15", "description": "Groceries", "category": "Food", "amount": "($1,234.56)"},
                {"date": "2026-04-16", "description": "Blank", "category": "Other", "amount": ""},
                {"date": "2026-04-17", "description": "Rent", "category": "Housing", "amount": "-1500"},
                {"date": "2026-04-18", "description": "Income", "category": "Paycheck", "amount": "3000"},
            ]
        )

        top_expenses = processor.get_top_expenses()

        assert [expense["description"] for expense in top_expenses] == ["Rent", "Groceries"]
        assert [expense["amount"] for expense in top_expenses] == [-1500.0, -1234.56]
