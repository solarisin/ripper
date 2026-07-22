"""Tiller data processing utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

import pandas as pd

# Category names (lowercased, whitespace-stripped) that identify account-to-account
# transfer transactions rather than real income or expenses. This is the FALLBACK
# classifier, used only when the authoritative Tiller Categories "Type" column is
# unavailable: a category absent from the ``category_types`` map (or no map at all)
# is classified by matching its name here. Both legs of a transfer (negative outgoing,
# positive incoming) match, so neither is miscounted as spending or income. Users who
# rename their transfer categories are covered by the Type metadata instead (issue #115).
TRANSFER_CATEGORIES: frozenset[str] = frozenset({"transfer", "transfers", "credit card payment"})


def parse_transaction_date(value: Any) -> datetime | None:
    """Parse a raw Tiller date cell into a naive :class:`datetime`, or ``None``.

    This is the single date parser shared by the dashboard service's date-range
    filter (``DashboardDataService._record_in_date_range``) and this module's
    :meth:`TillerDataProcessor._preprocess_data`, so both layers agree on exactly
    which rows fall inside a range (issue #44). It uses pandas ``to_datetime`` --
    the more lenient of the two former implementations -- coercing unparseable
    values to ``None`` and dropping any timezone so results compare cleanly with
    the naive range bounds returned by ``DateRange.get_date_range``.
    """
    if value is None:
        return None
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    parsed: datetime = timestamp.to_pydatetime()
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


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

    def __init__(
        self,
        transactions: List[TillerTransaction] | List[Dict[str, Any]],
        category_types: Dict[str, str] | None = None,
    ):
        """Initialize with transaction data.

        Args:
            transactions: List of transaction dictionaries
            category_types: Optional authoritative ``{category_name: type}`` map
                sourced from the Tiller Categories sheet's "Type" column
                (Income/Expense/Transfer). When supplied, a transaction whose
                category has ``Type == "Transfer"`` is excluded from spending
                aggregations and ``Type == "Income"`` is excluded as income. Keys
                and values are matched case-insensitively (whitespace-stripped).
                A category absent from the map -- or the map being ``None`` -- falls
                back to the name-based :data:`TRANSFER_CATEGORIES` classifier so
                every existing call site keeps its current behavior (issue #115).
        """
        self.df = pd.DataFrame(transactions)
        # Normalize both keys and values so lookups/comparisons are case- and
        # whitespace-insensitive, mirroring the name-based fallback.
        self._category_types: dict[str, str] = {
            str(name).strip().lower(): str(ctype).strip().lower()
            for name, ctype in (category_types or {}).items()
            if str(name).strip() and str(ctype).strip()
        }
        self._preprocess_data()

    def _preprocess_data(self) -> None:
        """Clean and preprocess the transaction data."""
        if self.df.empty:
            return

        # Convert date strings to datetime by mapping the SAME scalar parser the service-side
        # filter uses (``parse_transaction_date``) over each cell, so the two layers can never
        # disagree on a row's date (#44). A single vectorized ``pd.to_datetime(series)`` is NOT
        # equivalent: it infers one format from the first row and coerces differently-formatted
        # but valid dates (e.g. "01/16/2024" after a leading "2024-01-15") to NaT, silently
        # dropping rows the service accepted. The outer ``to_datetime`` only re-boxes the
        # already-parsed naive datetimes into a ``datetime64`` column for the ``.dt`` accessors
        # below; it does no format inference (the values are datetimes, not strings).
        self.df["date"] = pd.to_datetime(self.df["date"].map(parse_transaction_date))

        # Ensure amount is numeric. Tiller exports may include currency symbols,
        # thousands separators, blanks, or accounting-style parenthesized values.
        self.df["amount"] = self.df["amount"].apply(self._parse_amount)

        # Add month and year columns for easier grouping
        self.df["month"] = self.df["date"].dt.to_period("M")
        self.df["year"] = self.df["date"].dt.year

    @staticmethod
    def _parse_amount(value: Any) -> float | None:
        """Parse a Tiller amount cell into a float."""
        if pd.isna(value):
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        if not text:
            return None

        is_parenthesized = text.startswith("(") and text.endswith(")")
        if is_parenthesized:
            text = text[1:-1]

        cleaned = text.replace("$", "").replace(",", "").replace(" ", "").replace("\u2212", "-").strip()
        if not cleaned:
            return None

        try:
            amount = float(cleaned)
        except ValueError:
            return None

        return -abs(amount) if is_parenthesized else amount

    def _non_spending_mask(self) -> pd.Series:
        """Boolean mask of rows that must NOT count toward spending aggregations.

        A row is excluded when its category is a transfer (both legs of an
        account-to-account transfer) or income. Classification prefers the
        authoritative Tiller Categories ``Type`` metadata (via the optional
        ``category_types`` map) and falls back, per category, to the name-based
        :data:`TRANSFER_CATEGORIES` frozenset when a category is absent from the
        map or no map was supplied (issue #115).
        """
        normalized = self.df["category"].astype(str).str.strip().str.lower()
        if self._category_types:
            mapped = normalized.map(self._category_types)
            in_map = mapped.notna()
            typed_excluded = mapped.isin(("transfer", "income"))
            # Categories the Type metadata doesn't cover fall back to name matching.
            name_transfer = normalized.isin(TRANSFER_CATEGORIES)
            return (in_map & typed_excluded) | (~in_map & name_transfer)
        return normalized.isin(TRANSFER_CATEGORIES)

    def _without_transfers(self) -> pd.DataFrame:
        """Return the transactions with transfer- and income-category rows removed.

        Rows classified as transfers or income (see :meth:`_non_spending_mask`)
        are dropped so that neither leg of an account-to-account transfer, nor an
        income-typed row, is counted as spending.
        """
        if self.df.empty or "category" not in self.df.columns:
            return self.df
        return self.df[~self._non_spending_mask()]

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
        """Get monthly spending data (expenses only).

        Transfer-category transactions (both legs) and income/positive-amount
        transactions are excluded, so each month's value is the total expense
        magnitude for that month. Months with no expenses do not appear in the
        result.

        Returns:
            List of dicts with 'month' and 'amount' keys, where 'amount' is a
            positive expense magnitude
        """
        if self.df.empty:
            return []

        # Exclude transfers first (their outgoing leg is negative and would
        # otherwise count as spending), then filter to expenses and sum magnitudes
        non_transfers = self._without_transfers()
        expenses = non_transfers[non_transfers["amount"] < 0]
        if expenses.empty:
            return []

        monthly = expenses.groupby("month")["amount"].sum().abs().reset_index()
        monthly["month"] = monthly["month"].astype(str)

        return monthly.to_dict("records")  # type: ignore[return-value]

    def get_category_breakdown(self) -> List[Dict[str, Any]]:
        """Get spending breakdown by category (expenses only).

        Transfer-category transactions (both legs) and income/positive-amount
        transactions are excluded, so each category's value is its total
        expense magnitude. Categories with no expenses do not appear in the
        result.

        Returns:
            List of dicts with 'category' and 'amount' keys, where 'amount' is
            a positive expense magnitude, sorted descending by amount
        """
        if self.df.empty:
            return []

        # Exclude transfers first, then filter to expenses and sum magnitudes
        non_transfers = self._without_transfers()
        expenses = non_transfers[non_transfers["amount"] < 0]
        if expenses.empty:
            return []

        categories = expenses.groupby("category")["amount"].sum().abs().reset_index()
        categories = categories.sort_values("amount", ascending=False)

        return categories.to_dict("records")  # type: ignore[return-value]

    def get_top_expenses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top expenses by amount.

        Transfer-category transactions are excluded so an outgoing transfer
        leg (a large negative amount) does not appear as a top expense.

        Args:
            limit: Maximum number of expenses to return

        Returns:
            List of transactions sorted by amount (descending)
        """
        if self.df.empty:
            return []

        # Exclude transfers first, then get top expenses (largest absolute amounts)
        expenses = self._without_transfers().dropna(subset=["amount"])
        expenses = expenses[expenses["amount"] < 0].copy()
        if expenses.empty:
            return []

        expenses["abs_amount"] = expenses["amount"].abs()
        top_expenses = expenses.nlargest(limit, "abs_amount", keep="all").drop(columns=["abs_amount"])
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
