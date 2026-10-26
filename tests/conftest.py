from __future__ import annotations

import datetime as dt

import pytest

from uk_parl_written_questions.holidays import BankHolidays


@pytest.fixture
def bank_holidays() -> BankHolidays:
    """
    Supply the calendar needed by the June-to-September 2026 test cohorts.
    """
    return BankHolidays(
        source="test fixture",
        first_year=2026,
        last_year=2026,
        dates={dt.date(2026, 8, 31)},
    )
