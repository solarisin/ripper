"""Financial-specific widget implementations for Tiller data."""

from __future__ import annotations

from typing import Any

from loguru import logger
from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QPieSeries,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .dashboard import Dashboard
from .tiller_data import TillerDataProcessor
from .widget_types import WidgetType
from .widgets import BaseWidget, WidgetConfig, register_widget

# Default colors for charts
CHART_COLORS = [
    "#2ecc71",  # emerald
    "#3498db",  # peter river
    "#9b59b6",  # amethyst
    "#f1c40f",  # sunflower
    "#e67e22",  # carrot
    "#e74c3c",  # alizarin
    "#1abc9c",  # turquoise
    "#3498db",  # peter river
    "#9b59b6",  # amethyst
    "#34495e",  # wet asphalt
]


@register_widget(WidgetType.SPENDING_TREND)
class SpendingTrendWidget(BaseWidget):
    """Shows monthly spending trends over time."""

    def __init__(self, config: WidgetConfig, dashboard: Dashboard) -> None:
        super().__init__(config, dashboard)
        self.chart_view: QChartView | None = None
        self.data_processor: TillerDataProcessor | None = None

    def create_widget(self, parent: QWidget) -> QWidget:
        """Create and return the widget.

        Args:
            parent: Parent widget

        Returns:
            The created widget
        """
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create chart view with initial empty state
        self.chart_view = self._create_empty_chart_view()
        layout.addWidget(self.chart_view)

        # Initial data load if data source is available
        self.update_data()

        return container

    def _create_empty_chart_view(self) -> QChartView:
        """Create an empty chart view with a message."""
        chart = QChart()
        chart.setTitle("Monthly Spending Trend")
        chart.setTheme(QChart.ChartTheme.ChartThemeLight)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        # Add empty series to initialize axes
        series = QLineSeries()
        series.setName("Spending")
        chart.addSeries(series)
        chart.createDefaultAxes()

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        return chart_view

    def _update_chart(self, data: list[dict[str, Any]]) -> None:
        """Update the chart with new data.

        Args:
            data: List of dicts with 'month' and 'amount' keys
        """
        if not self.chart_view:
            return

        chart = self.chart_view.chart()
        chart.removeAllSeries()

        if not data:
            return

        # Create series for spending data
        series = QLineSeries()
        series.setName("Spending")

        # Add data points. get_monthly_spending() already returns expense-only
        # positive magnitudes; abs() is kept as a display-safety no-op.
        for i, item in enumerate(data):
            amount = abs(float(item.get("amount", 0)))
            series.append(i, amount)

        # Add series to chart
        chart.addSeries(series)

        # Configure axes. createDefaultAxes() attaches auto-ranged value axes to
        # the series; access them via the Qt6 axes() API to title them.
        chart.createDefaultAxes()

        # Customize appearance
        horizontal_axes = chart.axes(Qt.Orientation.Horizontal)
        vertical_axes = chart.axes(Qt.Orientation.Vertical)
        if horizontal_axes:
            horizontal_axes[0].setTitleText("Month")
        if vertical_axes:
            vertical_axes[0].setTitleText("Amount ($)")

        # Update chart view
        self.chart_view.update()

    def update_data(self, service: Any = None) -> None:
        """Update the widget's data from its data source."""
        if not self.config.data_source_id:
            return

        data = self._runtime_data(service)
        if not data:
            return

        try:
            # Records arrive already filtered by the data source's date range (and account/
            # category filters) in DashboardDataService._apply_filters, so the widget consumes
            # them as-is and does NOT re-apply the date range -- a single, shared filter pass
            # avoids the two layers disagreeing on boundary rows (#44).
            self.data_processor = TillerDataProcessor(data)

            # Get monthly spending data
            monthly_data = self.data_processor.get_monthly_spending()

            # Update the chart
            self._update_chart(monthly_data)

        except Exception as e:
            logger.error(f"Error updating spending trend: {e}")

    def _runtime_data(self, service: Any = None) -> list[dict[str, Any]]:
        if isinstance(service, dict) and self.config.data_source_id:
            data = service.get(self.config.data_source_id)
            if isinstance(data, list):
                return data
        return []


@register_widget(WidgetType.CATEGORY_BREAKDOWN)
class CategoryBreakdownWidget(BaseWidget):
    """Shows a breakdown of spending by category."""

    def __init__(self, config: WidgetConfig, dashboard: Dashboard) -> None:
        super().__init__(config, dashboard)
        self.chart_view: QChartView | None = None
        self.data_processor: TillerDataProcessor | None = None
        self.min_percentage = 2.0  # Minimum percentage to show as individual slice

    def create_widget(self, parent: QWidget) -> QWidget:
        """Create and return the widget.

        Args:
            parent: Parent widget

        Returns:
            The created widget
        """
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create chart view with initial empty state
        self.chart_view = self._create_empty_chart_view()
        layout.addWidget(self.chart_view)

        # Initial data load if data source is available
        self.update_data()

        return container

    def _create_empty_chart_view(self) -> QChartView:
        """Create an empty chart view with a message."""
        chart = QChart()
        chart.setTitle("Spending by Category")
        chart.setTheme(QChart.ChartTheme.ChartThemeLight)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        chart.setAnimationOptions(QChart.AnimationOption.AllAnimations)

        # Add empty series
        series = QPieSeries()
        series.setHoleSize(0.3)  # Create a donut chart
        chart.addSeries(series)

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        return chart_view

    def _update_chart(self, category_data: list[dict[str, Any]]) -> None:
        """Update the chart with new data.

        Args:
            category_data: List of dicts with 'category' and 'amount' keys
        """
        if not self.chart_view:
            return

        chart = self.chart_view.chart()
        # Always clear existing series so a refresh with no data doesn't leave
        # stale slices from a previous render.
        chart.removeAllSeries()

        if not category_data:
            return

        # Create new series
        series = QPieSeries()
        series.setHoleSize(0.3)  # Create a donut chart

        # Calculate total for percentage calculations. get_category_breakdown()
        # already returns expense-only positive magnitudes; abs() is kept as a
        # display-safety no-op.
        total = sum(abs(item.get("amount", 0)) for item in category_data)
        if total <= 0:
            return

        # Add slices to the pie chart
        other_amount = 0.0
        other_categories = []

        for i, item in enumerate(category_data):
            category = str(item.get("category", "Unknown"))
            amount = abs(float(item.get("amount", 0)))
            percentage = (amount / total) * 100

            if percentage < self.min_percentage:
                other_amount += amount
                other_categories.append(category)
                continue

            # Add slice to the pie chart
            slice_ = series.append(f"{category} ({percentage:.1f}%)", amount)
            slice_.setColor(QColor(CHART_COLORS[i % len(CHART_COLORS)]))

            # Show labels for larger slices
            slice_.setLabelVisible(percentage >= 5.0)

        # Add "Other" category if needed
        if other_amount > 0:
            other_percentage = (other_amount / total) * 100
            slice_ = series.append(f"Other ({other_percentage:.1f}%)", other_amount)
            slice_.setColor(QColor("#95a5a6"))  # Concrete color for "Other"

        # Add series to chart
        chart.addSeries(series)

        # Update chart view
        self.chart_view.update()

    def update_data(self, service: Any = None) -> None:
        """Update the widget's data from its data source."""
        if not self.config.data_source_id:
            return

        data = self._runtime_data(service)
        if not data:
            return

        try:
            # Records arrive already filtered by the data source's date range in the service
            # layer, so the widget renders them without re-applying the range (#44).
            self.data_processor = TillerDataProcessor(data)

            # Get category breakdown data
            category_data = self.data_processor.get_category_breakdown()

            # Update the chart
            self._update_chart(category_data)

        except Exception as e:
            logger.error(f"Error updating category breakdown: {e}")

    def _runtime_data(self, service: Any = None) -> list[dict[str, Any]]:
        if isinstance(service, dict) and self.config.data_source_id:
            data = service.get(self.config.data_source_id)
            if isinstance(data, list):
                return data
        return []


@register_widget(WidgetType.BUDGET_VS_ACTUAL)
class BudgetVsActualWidget(BaseWidget):
    """Shows budget vs actual spending comparison."""

    def __init__(self, config: WidgetConfig, dashboard: Dashboard) -> None:
        super().__init__(config, dashboard)
        self.chart_view: QChartView | None = None
        self.data_processor: Any = None
        self.budget_data: dict[str, float] = {}

    def create_widget(self, parent: QWidget) -> QWidget:
        """Create and return the widget.

        Args:
            parent: Parent widget

        Returns:
            The created widget
        """
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create chart view with initial empty state
        self.chart_view = self._create_empty_chart_view()
        layout.addWidget(self.chart_view)

        # Initial data load if data source is available
        self.update_data()

        return container

    def _create_empty_chart_view(self) -> QChartView:
        """Create an empty chart view with a message."""
        chart = QChart()
        chart.setTitle("Budget vs Actual")
        chart.setTheme(QChart.ChartTheme.ChartThemeLight)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        chart.setAnimationOptions(QChart.AnimationOption.AllAnimations)

        # Add empty series to initialize axes
        series = QBarSeries()
        chart.addSeries(series)
        chart.createDefaultAxes()

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        return chart_view

    def _update_chart(self, comparison_data: list[dict[str, Any]]) -> None:
        """Update the chart with new data.

        Args:
            comparison_data: List of dicts with 'category', 'budgeted', and 'actual' keys
        """
        if not self.chart_view or not comparison_data:
            return

        chart = self.chart_view.chart()
        chart.removeAllSeries()

        # Create series for budgeted and actual amounts
        budget_set = QBarSet("Budgeted")
        actual_set = QBarSet("Actual")
        categories = []

        # Add data to the series
        for item in comparison_data:
            category = str(item.get("category", "Unknown"))
            budgeted = float(item.get("budgeted", 0))
            actual = abs(float(item.get("amount", 0)))  # Amount is negative for expenses

            # Only show categories with budget or actual amounts
            if budgeted > 0 or actual > 0:
                budget_set << budgeted
                actual_set << actual
                categories.append(category)

        if not categories:  # No data to display
            return

        # Create and configure the bar series
        series = QBarSeries()
        series.append(budget_set)
        series.append(actual_set)
        chart.addSeries(series)

        # Configure axes (Qt6 addAxis/attachAxis API). createDefaultAxes() gives
        # an auto-ranged value axis on each orientation; replace the horizontal one
        # with a category axis so the bars are labelled by category.
        chart.createDefaultAxes()
        for axis in chart.axes(Qt.Orientation.Horizontal):
            series.detachAxis(axis)
            chart.removeAxis(axis)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setTitleText("Category")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        vertical_axes = chart.axes(Qt.Orientation.Vertical)
        if vertical_axes:
            vertical_axes[0].setTitleText("Amount ($)")

        # Style the bars
        budget_set.setColor(QColor("#2ecc71"))  # Green for budgeted
        actual_set.setColor(QColor("#e74c3c"))  # Red for actual (overspending)

        # Update chart view
        self.chart_view.update()

    def update_data(self, service: Any = None) -> None:
        """Show the unsupported state until budget sources are implemented."""
        if self.chart_view:
            self.chart_view.chart().setTitle("Budget data sources are not supported yet")

    def _get_budget_data(self) -> dict[str, float]:
        """Get budget data for categories.

        Returns:
            Dictionary mapping category names to budgeted amounts
        """
        # This is a placeholder implementation
        # In a real app, you would load this from a budget data source
        return {}


@register_widget(WidgetType.TOP_EXPENSES)
class TopExpensesWidget(BaseWidget):
    """Shows a table of the top expenses."""

    def __init__(self, config: WidgetConfig, dashboard: Dashboard) -> None:
        super().__init__(config, dashboard)
        self.table: QTableWidget | None = None
        self.data_processor: TillerDataProcessor | None = None
        self.num_expenses = 10  # Number of top expenses to show

    def create_widget(self, parent: QWidget) -> QWidget:
        """Create and return the widget.

        Args:
            parent: Parent widget

        Returns:
            The created widget
        """
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create table widget
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date", "Description", "Category", "Amount"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Description
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Category
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Amount

        # Set initial empty state
        self._show_empty_state()

        layout.addWidget(self.table)
        return container

    def _show_empty_state(self) -> None:
        """Show an empty state in the table."""
        if not self.table:
            return

        # Clear any stale data or spans from a previous real-data render before
        # setting the spanning empty-state cell, so hidden items don't persist.
        self.table.clearSpans()
        self.table.clearContents()
        self.table.setRowCount(1)
        self.table.setRowHidden(0, False)

        # Create a centered item with a message
        empty_item = QTableWidgetItem("No expense data available")
        empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

        # Set the item to span all columns
        self.table.setSpan(0, 0, 1, 4)
        self.table.setItem(0, 0, empty_item)

        # Disable sorting while in empty state
        self.table.setSortingEnabled(False)

    def update_data(self, service: Any = None) -> None:
        """Update the widget's data from its data source."""
        if not self.config.data_source_id or not self.table:
            return

        data = self._runtime_data(service)
        if not data:
            self._show_empty_state()
            return

        try:
            # Records arrive already filtered by the data source's date range in the service
            # layer, so the widget renders them without re-applying the range (#44).
            self.data_processor = TillerDataProcessor(data)

            top_expenses = self.data_processor.get_top_expenses(self.num_expenses)

            if not top_expenses:
                self._show_empty_state()
                return

            # Clear existing rows; reset spans first so the empty-state span
            # set by _show_empty_state() does not persist into the data view.
            self.table.clearSpans()
            self.table.clearContents()
            self.table.setSortingEnabled(False)  # Disable sorting while updating
            self.table.setRowCount(len(top_expenses))

            # Add data to the table
            for row, expense in enumerate(top_expenses):
                # Date
                date_item = QTableWidgetItem(
                    expense.get("date", "").strftime("%Y-%m-%d")
                    if hasattr(expense.get("date"), "strftime")
                    else str(expense.get("date", ""))
                )
                self.table.setItem(row, 0, date_item)

                # Description
                desc_item = QTableWidgetItem(str(expense.get("description", "")))
                self.table.setItem(row, 1, desc_item)

                # Category
                category_item = QTableWidgetItem(str(expense.get("category", "Uncategorized")))
                self.table.setItem(row, 2, category_item)

                # Amount (formatted as currency)
                amount = float(expense.get("amount", 0))
                amount_item = QTableWidgetItem(f"${abs(amount):,.2f}")
                amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                # Color code negative amounts (expenses) in red
                if amount < 0:
                    amount_item.setForeground(QColor("#e74c3c"))
                self.table.setItem(row, 3, amount_item)

            # Re-enable sorting and sort by date (newest first)
            self.table.setSortingEnabled(True)
            self.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)

            # Reset the horizontal header after sorting is enabled
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        except Exception as e:
            logger.error(f"Error updating top expenses: {e}")
            self._show_empty_state()

    def _runtime_data(self, service: Any = None) -> list[dict[str, Any]]:
        if isinstance(service, dict) and self.config.data_source_id:
            data = service.get(self.config.data_source_id)
            if isinstance(data, list):
                return data
        return []
