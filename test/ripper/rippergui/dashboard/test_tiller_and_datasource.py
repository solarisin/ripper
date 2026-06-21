"""Headless tests for Tiller data processing and DataSource/DateRange models.

These exercise the pure-Python dashboard model layer (no Qt), covering the
TillerDataProcessor aggregations, DateRange presets, and DataSource
(de)serialization that previously had no dedicated coverage (see issue #59).
"""

from datetime import datetime, timedelta

import pytest

from ripper.rippergui.dashboard.models.data_source import (
    DataSource,
    DataSourceType,
    DateRange,
    DateRangePreset,
)
from ripper.rippergui.dashboard.models.tiller_data import TillerDataProcessor

SAMPLE_TRANSACTIONS = [
    {"date": "2024-01-05", "description": "Coffee", "category": "Food", "amount": -5.0, "account": "Visa"},
    {"date": "2024-01-20", "description": "Salary", "category": "Income", "amount": 1000.0, "account": "Bank"},
    {"date": "2024-02-10", "description": "Rent", "category": "Housing", "amount": -800.0, "account": "Bank"},
    {"date": "2024-02-15", "description": "Groceries", "category": "Food", "amount": -150.0, "account": "Visa"},
]


def _processor():
    return TillerDataProcessor(SAMPLE_TRANSACTIONS)


# --------------------------------------------------------------------------- #
# _parse_amount
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        (42, 42.0),
        (-7.5, -7.5),
        ("$1,234.56", 1234.56),
        ("(50.00)", -50.0),  # accounting-style parentheses => negative
        ("−5", -5.0),  # unicode minus sign
        ("  $ 12.00 ", 12.0),
        ("", None),
        ("   ", None),
        ("abc", None),
        (None, None),
    ],
)
def test_parse_amount_variants(raw, expected):
    assert TillerDataProcessor._parse_amount(raw) == expected


def test_empty_processor_returns_empty_aggregations():
    processor = TillerDataProcessor([])
    assert processor.get_monthly_spending() == []
    assert processor.get_category_breakdown() == []
    assert processor.get_top_expenses() == []
    assert processor.get_budget_vs_actual({"Food": 100.0}) == []
    assert processor.get_net_worth_over_time() == []


# --------------------------------------------------------------------------- #
# Aggregations
# --------------------------------------------------------------------------- #
def test_get_monthly_spending_sums_by_month():
    result = {row["month"]: row["amount"] for row in _processor().get_monthly_spending()}
    assert result["2024-01"] == 995.0  # -5 + 1000
    assert result["2024-02"] == -950.0  # -800 - 150


def test_get_category_breakdown_sorted_descending():
    breakdown = _processor().get_category_breakdown()
    amounts = {row["category"]: row["amount"] for row in breakdown}
    assert amounts == {"Income": 1000.0, "Food": -155.0, "Housing": -800.0}
    # Sorted by amount descending.
    assert [row["amount"] for row in breakdown] == sorted((row["amount"] for row in breakdown), reverse=True)


def test_get_top_expenses_returns_largest_absolute_negative_amounts():
    top = _processor().get_top_expenses(limit=2)
    descriptions = [row["description"] for row in top]
    assert descriptions == ["Rent", "Groceries"]


def test_get_top_expenses_excludes_income():
    income_only = TillerDataProcessor(
        [{"date": "2024-01-01", "description": "Pay", "category": "Income", "amount": 500.0, "account": "Bank"}]
    )
    assert income_only.get_top_expenses() == []


def test_get_budget_vs_actual_computes_remaining():
    result = {row["category"]: row for row in _processor().get_budget_vs_actual({"Food": 200.0, "Housing": 1000.0})}
    # amount is negative for expenses; remaining = budgeted + amount
    assert result["Food"]["remaining"] == 45.0  # 200 - 155
    assert result["Housing"]["remaining"] == 200.0  # 1000 - 800


def test_get_net_worth_over_time_is_cumulative():
    series = _processor().get_net_worth_over_time()
    assert series[-1]["net_worth"] == 45.0  # -5 + 1000 - 800 - 150


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #
def test_filter_by_date_range_is_inclusive():
    filtered = _processor().filter_by_date_range(datetime(2024, 2, 1), datetime(2024, 2, 28))
    descriptions = sorted(filtered.df["description"].tolist())
    assert descriptions == ["Groceries", "Rent"]


def test_filter_by_categories_keeps_only_requested():
    filtered = _processor().filter_by_categories(["Food"])
    assert sorted(filtered.df["description"].tolist()) == ["Coffee", "Groceries"]


def test_filter_by_categories_empty_list_is_passthrough():
    processor = _processor()
    assert processor.filter_by_categories([]) is processor


# --------------------------------------------------------------------------- #
# DateRange presets
# --------------------------------------------------------------------------- #
def test_date_range_last_30_days():
    start, end = DateRange(DateRangePreset.LAST_30_DAYS).get_date_range()
    assert (end - start) == timedelta(days=30)


def test_date_range_last_90_days():
    start, end = DateRange(DateRangePreset.LAST_90_DAYS).get_date_range()
    assert (end - start) == timedelta(days=90)


def test_date_range_year_to_date_starts_january_first():
    start, end = DateRange(DateRangePreset.YEAR_TO_DATE).get_date_range()
    assert (start.month, start.day) == (1, 1)
    assert start.year == end.year


def test_date_range_last_year_is_full_previous_year():
    start, end = DateRange(DateRangePreset.LAST_YEAR).get_date_range()
    assert start == datetime(datetime.now().year - 1, 1, 1)
    assert (end.month, end.day) == (12, 31)


def test_date_range_current_month_starts_on_the_first():
    start, end = DateRange(DateRangePreset.CURRENT_MONTH).get_date_range()
    assert start.day == 1
    assert end >= start


def test_date_range_custom_uses_provided_dates():
    start_in, end_in = datetime(2020, 3, 1), datetime(2020, 3, 31)
    start, end = DateRange(DateRangePreset.CUSTOM, start_date=start_in, end_date=end_in).get_date_range()
    assert (start, end) == (start_in, end_in)


def test_date_range_custom_without_dates_falls_back_to_30_days():
    start, end = DateRange(DateRangePreset.CUSTOM).get_date_range()
    assert (end - start) == timedelta(days=30)


# --------------------------------------------------------------------------- #
# DataSource serialization
# --------------------------------------------------------------------------- #
def test_data_source_round_trip_custom_range():
    source = DataSource(
        id="src-1",
        type=DataSourceType.TILLER_TRANSACTIONS,
        name="Transactions",
        spreadsheet_id="sheet-1",
        sheet_name="Transactions",
        range_a1="A1:E10",
        date_range=DateRange(
            DateRangePreset.CUSTOM,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        ),
        filters={"accounts": ["Visa"]},
    )

    restored = DataSource.from_dict(source.to_dict())

    assert restored.id == source.id
    assert restored.type == DataSourceType.TILLER_TRANSACTIONS
    assert restored.range_a1 == "A1:E10"
    assert restored.filters == {"accounts": ["Visa"]}
    assert restored.date_range.preset == DateRangePreset.CUSTOM
    assert restored.date_range.start_date == datetime(2024, 1, 1)
    assert restored.date_range.end_date == datetime(2024, 12, 31)


def test_data_source_from_dict_defaults_missing_date_range():
    minimal = {
        "id": "src-2",
        "type": DataSourceType.TILLER_BUDGET.value,
        "name": "Budget",
        "spreadsheet_id": "sheet-2",
        "sheet_name": "Budget",
        "range_a1": "A1:B5",
    }
    restored = DataSource.from_dict(minimal)
    assert restored.type == DataSourceType.TILLER_BUDGET
    assert restored.date_range.preset == DateRangePreset.LAST_30_DAYS
    assert restored.filters == {}
