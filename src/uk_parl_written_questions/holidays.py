from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Self

import httpx
from pydantic import BaseModel, Field, model_validator

RECURRING_HOLIDAYS = frozenset(
    {
        "New Year's Day",
        "Good Friday",
        "Easter Monday",
        "Early May bank holiday",
        "Spring bank holiday",
        "Summer bank holiday",
        "Christmas Day",
        "Boxing Day",
    }
)


class BankHolidays(BaseModel):
    """
    Hold the checked-in England and Wales calendar and its coverage.
    """

    source: str
    first_year: int
    last_year: int
    dates: set[dt.date]
    refreshed_at: dt.datetime | None = None

    def is_working_day(self, date: dt.date) -> bool:
        """
        Check calendar coverage before excluding weekends and bank holidays.
        """
        if not self.first_year <= date.year <= self.last_year:
            raise ValueError("Update bank_holidays.json to cover the assessment period")
        return date.weekday() < 5 and date not in self.dates

    def working_days_after(self, deadline: dt.date, until: dt.date) -> int:
        """
        Count working days strictly after the deadline, including the end date.
        """
        current = deadline
        count = 0
        while current < until:
            current += dt.timedelta(days=1)
            count += int(self.is_working_day(current))
        return count

    def ordinary_target_date(self, date_for_answer: dt.date) -> dt.date:
        """
        Return the fifth working day on or after the published answer date.

        Count date_for_answer as day one when it is a working day. Skip
        weekends and bank holidays, but do not exclude parliamentary recesses.
        """
        current = date_for_answer
        remaining = 5
        while remaining:
            if self.is_working_day(current):
                remaining -= 1
            if remaining:
                current += dt.timedelta(days=1)
        return current


def load_bank_holidays(repo_root: Path | None = None) -> BankHolidays:
    """
    Load the official calendar snapshot without requiring a network request.
    """
    return BankHolidays.model_validate_json(
        ((repo_root or Path.cwd()) / "data/raw/bank_holidays.json").read_text()
    )


class HolidayEvent(BaseModel):
    """
    Read the name and date from a GOV.UK bank holiday event.
    """

    title: str
    date: dt.date


class HolidayDivision(BaseModel):
    """
    Require the recurring holidays in every year before replacing the cache.
    """

    events: list[HolidayEvent] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_years(self) -> Self:
        """
        Reject partial years and gaps, allowing moved dates and extra holidays.

        GOV.UK adds parenthetical qualifiers such as "(VE day)" to some names.
        This checks recurring holidays; it cannot discover an omitted one-off
        holiday that has never appeared in the source.
        """
        years = {event.date.year for event in self.events}
        for year in range(min(years), max(years) + 1):
            events = [event for event in self.events if event.date.year == year]
            names = {event.title.split(" (")[0].replace("’", "'") for event in events}
            missing = RECURRING_HOLIDAYS - names
            if missing:
                raise ValueError(
                    f"Incomplete bank holiday year {year}: missing {', '.join(sorted(missing))}"
                )
            if len({event.date for event in events}) < len(RECURRING_HOLIDAYS):
                raise ValueError(
                    f"Incomplete bank holiday year {year}: duplicate dates"
                )
        return self


def refresh_bank_holidays(repo_root: Path | None = None) -> BankHolidays:
    """
    Refresh the England and Wales snapshot from GOV.UK during project fetch.

    Validate before replacing the cache; request failures leave it unchanged.
    """
    source = "https://www.gov.uk/bank-holidays.json"
    response = httpx.get(source, timeout=30, follow_redirects=True)
    response.raise_for_status()
    division = HolidayDivision.model_validate(response.json()["england-and-wales"])
    dates = {event.date for event in division.events}
    calendar = BankHolidays(
        source=source,
        first_year=min(dates).year,
        last_year=max(dates).year,
        dates=dates,
        refreshed_at=dt.datetime.now(dt.timezone.utc),
    )
    path = (repo_root or Path.cwd()) / "data/raw/bank_holidays.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sort dates so each refresh produces a stable, reviewable cache file.
    contents = calendar.model_dump(mode="json")
    contents["dates"] = sorted(contents["dates"])
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(contents, indent=2) + "\n")
    temporary.replace(path)
    return calendar
