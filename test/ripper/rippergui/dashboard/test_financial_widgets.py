"""Tests for financial dashboard models."""

import pytest
from PySide6.QtWidgets import QWidget

from ripper.rippergui.dashboard.models.dashboard import Dashboard
from ripper.rippergui.dashboard.models.financial_widgets import (
    BudgetVsActualWidget,
    CategoryBreakdownWidget,
    SpendingTrendWidget,
)
from ripper.rippergui.dashboard.models.widget_types import WidgetType
from ripper.rippergui.dashboard.models.widgets import WidgetConfig


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
