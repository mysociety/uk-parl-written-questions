from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from uk_parl_written_questions import __main__ as cli
from uk_parl_written_questions import holidays


@pytest.fixture
def holiday_events() -> list[dict[str, str]]:
    """
    Include each recurring England and Wales holiday in two complete years.
    """
    names = [
        "New Year’s Day",
        "Good Friday",
        "Easter Monday",
        "Early May bank holiday",
        "Spring bank holiday",
        "Summer bank holiday",
        "Christmas Day",
        "Boxing Day",
    ]
    dates = [
        "2026-01-01",
        "2026-04-03",
        "2026-04-06",
        "2026-05-04",
        "2026-05-25",
        "2026-08-31",
        "2026-12-25",
        "2026-12-28",
        "2027-01-01",
        "2027-03-26",
        "2027-03-29",
        "2027-05-03",
        "2027-05-31",
        "2027-08-30",
        "2027-12-27",
        "2027-12-28",
    ]
    return [
        {"title": title, "date": date}
        for title, date in zip(names * 2, dates, strict=True)
    ]


def test_refresh_and_load_from_selected_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    holiday_events: list[dict[str, str]],
) -> None:
    """
    Refresh the selected raw cache and derive coverage from the source dates.
    """
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "https://www.gov.uk/bank-holidays.json"),
        json={
            "england-and-wales": {"events": holiday_events},
            "scotland": {"events": [{"date": "2026-01-02"}]},
        },
    )
    monkeypatch.setattr(holidays.httpx, "get", lambda *args, **kwargs: response)
    calendar = holidays.refresh_bank_holidays(tmp_path)
    assert calendar.first_year == 2026
    assert calendar.last_year == 2027
    assert calendar.dates == {
        dt.date.fromisoformat(event["date"]) for event in holiday_events
    }
    assert calendar.ordinary_target_date(dt.date(2026, 8, 25)) == dt.date(2026, 9, 1)
    assert calendar.refreshed_at is not None
    assert holidays.load_bank_holidays(tmp_path) == calendar
    assert not (tmp_path / "data/raw/bank_holidays.json.tmp").exists()


@pytest.mark.parametrize("status", [200, 503])
def test_failed_or_empty_download_preserves_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """
    Never replace a usable cache with a failed response or empty calendar.
    """
    path = tmp_path / "data/raw/bank_holidays.json"
    path.parent.mkdir(parents=True)
    path.write_text("existing cache")
    response = httpx.Response(
        status,
        request=httpx.Request("GET", "https://www.gov.uk/bank-holidays.json"),
        json={"england-and-wales": {"events": []}},
    )
    monkeypatch.setattr(holidays.httpx, "get", lambda *args, **kwargs: response)
    with pytest.raises((httpx.HTTPStatusError, ValidationError)):
        holidays.refresh_bank_holidays(tmp_path)
    assert path.read_text() == "existing cache"


def test_project_fetch_refreshes_holidays(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Refresh the holiday cache before fetching recent questions.
    """
    calls: list[str] = []
    monkeypatch.setattr(cli, "refresh_bank_holidays", lambda: calls.append("holidays"))
    monkeypatch.setattr(
        cli,
        "get_all_data",
        lambda force_recent: calls.append(f"questions:{force_recent}"),
    )
    result = CliRunner().invoke(cli.app, ["fetch"])
    assert result.exit_code == 0, result.output
    assert calls == ["holidays", "questions:True"]


@pytest.mark.parametrize(
    "damage", ["partial_edges", "missing_year", "missing_holiday", "duplicate_dates"]
)
def test_incomplete_download_preserves_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    holiday_events: list[dict[str, str]],
    damage: str,
) -> None:
    """
    Reject gaps and partial years even when extra events conceal a missing day.
    """
    if damage == "partial_edges":
        holiday_events = [holiday_events[6], holiday_events[8]]
    elif damage == "missing_year":
        for event in holiday_events[8:]:
            event["date"] = event["date"].replace("2027", "2028")
    elif damage == "missing_holiday":
        holiday_events[5] = {"title": "Extra bank holiday", "date": "2026-07-01"}
    else:
        holiday_events[5]["date"] = holiday_events[4]["date"]
    path = tmp_path / "data/raw/bank_holidays.json"
    path.parent.mkdir(parents=True)
    path.write_text("existing cache")
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "https://www.gov.uk/bank-holidays.json"),
        json={"england-and-wales": {"events": holiday_events}},
    )
    monkeypatch.setattr(holidays.httpx, "get", lambda *args, **kwargs: response)
    with pytest.raises(ValidationError, match="Incomplete bank holiday year"):
        holidays.refresh_bank_holidays(tmp_path)
    assert path.read_text() == "existing cache"


def test_moved_and_extra_holidays_are_accepted(
    holiday_events: list[dict[str, str]],
) -> None:
    """
    Allow qualifiers and moved dates without requiring a fixed number of events.
    """
    holiday_events[3] = {
        "title": "Early May bank holiday (VE day)",
        "date": "2026-05-08",
    }
    holiday_events[4]["date"] = "2026-06-02"
    holiday_events.append({"title": "Extra bank holiday", "date": "2026-06-03"})
    division = holidays.HolidayDivision.model_validate({"events": holiday_events})
    assert len(division.events) == 17


@pytest.mark.parametrize(
    ("date_for_answer", "expected"),
    [
        ("2026-09-09", "2026-09-15"),
        ("2026-08-26", "2026-09-02"),
        ("2026-08-29", "2026-09-07"),
        ("2026-08-31", "2026-09-07"),
    ],
)
def test_ordinary_target_counts_answer_date_inclusively(
    bank_holidays: holidays.BankHolidays, date_for_answer: str, expected: str
) -> None:
    """
    Include a working start date and skip weekend or bank-holiday start dates.
    """
    assert bank_holidays.ordinary_target_date(
        dt.date.fromisoformat(date_for_answer)
    ) == dt.date.fromisoformat(expected)
