"""Tiller data processing utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

import pandas as pd


class TillerTransaction(TypedDict):
    """Represents a single Tiller transaction."""

    date: str
    description: str
    category: str
    amount: float
    account: str
    notes: Optional[str]
    tags: Optional[List[str]]


class TillerDataProcessor:
    """Processes Tiller transaction data for dashboard visualizations."""

    def __init__(self, transactions: List[TillerTransaction] | List[Dict[str, Any]]):
        """Initialize with transaction data.

        Args:
            transactions: List of transaction dictionaries
        """
        self.df = pd.DataFrame(transactions)
        self._preprocess_data()

    def _preprocess_data(self) -> None:
        """Clean and preprocess the transaction data."""
        if self.df.empty:
            return

        # Convert date strings to datetime
        self.df["date"] = pd.to_datetime(self.df["date"])

        # Ensure amount is numeric and expenses are negative
        self.df["amount"] = pd.to_numeric(self.df["amount"], errors="coerce")

        # Add month and year columns for easier grouping
        self.df["month"] = self.df["date"].dt.to_period("M")
        self.df["year"] = self.df["date"].dt.year

    def filter_by_date_range(self, start_date: datetime, end_date: datetime) -> "TillerDataProcessor":
        """Filter transactions by date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            New TillerDataProcessor with filtered data
        """
        mask = (self.df["date"] >= start_date) & (self.df["date"] <= end_date)
        filtered_data = self.df[mask].to_dict("records")
        return TillerDataProcessor(filtered_data)  # type: ignore[arg-type]

    def filter_by_categories(self, categories: List[str]) -> "TillerDataProcessor":
        """Filter transactions by categories.

        Args:
            categories: List of category names to include

        Returns:
            New TillerDataProcessor with filtered data
        """
        if not categories:
            return self
        filtered_data = self.df[self.df["category"].isin(categories)].to_dict("records")
        return TillerDataProcessor(filtered_data)  # type: ignore[arg-type]

    def get_monthly_spending(self) -> List[Dict[str, Any]]:
        """Get monthly spending data.

        Returns:
            List of dicts with 'month' and 'amount' keys
        """
        if self.df.empty:
            return []

        # Group by month and sum amounts
        monthly = self.df.groupby("month")["amount"].sum().reset_index()
        monthly["month"] = monthly["month"].astype(str)

        return monthly.to_dict("records")  # type: ignore[return-value]

    def get_category_breakdown(self) -> List[Dict[str, Any]]:
        """Get spending breakdown by category.

        Returns:
            List of dicts with 'category' and 'amount' keys
        """
        if self.df.empty:
            return []

        # Group by category and sum amounts
        categories = self.df.groupby("category")["amount"].sum().reset_index()
        categories = categories.sort_values("amount", ascending=False)

        return categories.to_dict("records")  # type: ignore[return-value]

    def get_top_expenses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top expenses by amount.

        Args:
            limit: Maximum number of expenses to return

        Returns:
            List of transactions sorted by amount (descending)
        """
        if self.df.empty:
            return []

        # Get top expenses (largest absolute amounts)
        top_expenses = self.df.nlargest(limit, "amount", keep="all")
        return top_expenses.to_dict("records")  # type: ignore[return-value]

    def get_budget_vs_actual(self, budget_data: Dict[str, float]) -> List[Dict[str, Any]]:
        """Compare actual spending vs budget by category.

        Args:
            budget_data: Dict mapping category names to budgeted amounts

        Returns:
            List of dicts with 'category', 'budgeted', and 'actual' keys
        """
        if self.df.empty or not budget_data:
            return []

        # Calculate actual spending by category
        actual_spending = self.df.groupby("category")["amount"].sum().reset_index()

        # Merge with budget data
        budget_df = pd.DataFrame([{"category": k, "budgeted": v} for k, v in budget_data.items()])
        comparison = pd.merge(budget_df, actual_spending, on="category", how="left").fillna(0)

        # Calculate remaining budget
        comparison["remaining"] = comparison["budgeted"] + comparison["amount"]  # amount is negative for expenses

        return comparison.to_dict("records")  # type: ignore[return-value]

    def get_net_worth_over_time(self, include_investments: bool = True) -> List[Dict[str, Any]]:
        """Calculate net worth over time.

        Args:
            include_investments: Whether to include investment accounts

        Returns:
            List of dicts with 'date' and 'net_worth' keys
        """
        if self.df.empty:
            return []

        # This is a simplified version - in a real implementation, you would need
        # to combine transaction data with account balances
        net_worth = self.df.groupby("date")["amount"].sum().cumsum().reset_index()
        net_worth.columns = ["date", "net_worth"]

        return net_worth.to_dict("records")  # type: ignore[return-value]
