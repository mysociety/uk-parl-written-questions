from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from uk_parl_written_questions.performance import (
    BankHolidays,
    Question,
    aggregate_performance,
    load_recent_questions,
)


def question(identifier: int, tabled: str, **changes: object) -> Question:
    """
    Make a source question with explicit dates for boundary tests.
    """
    return Question.model_validate(
        {
            "id": identifier,
            "dateTabled": tabled,
            "dateForAnswer": "2026-09-08T00:00:00",
            "answeringBodyId": 1,
            "answeringBodyName": "Home Office",
            "isNamedDay": False,
            **changes,
        }
    )


def test_cohorts_deadlines_holding_answers_and_totals(
    bank_holidays: BankHolidays,
) -> None:
    """
    Reconcile all rows across exact period, answer and deadline boundaries.
    """
    dataset = aggregate_performance(
        [
            question(1, "2026-09-07", dateAnswered="2026-09-14"),
            question(2, "2026-09-07", dateAnswered="2026-09-15"),
            question(3, "2026-09-07"),
            question(4, "2026-09-08", dateForAnswer="2026-09-09"),
            question(5, "2026-09-07", dateAnswered="2026-09-14", answerIsHolding=True),
            question(6, "2026-08-17"),  # First day of the 30-day window.
            question(7, "2026-08-16"),
            question(8, "2026-06-18"),  # First day of the 90-day window.
            question(9, "2026-06-17"),
            question(10, "2026-09-16"),
            question(11, "2026-09-07", isWithdrawn=True),
            question(12, "2026-09-07", answeringBodyId=9),
            question(
                13,
                "2026-09-07",
                isNamedDay=True,
                dateForAnswer="2026-09-14",
                dateAnswered="2026-09-14",
            ),
            question(14, "2026-09-07", isNamedDay=True, dateAnswered="2026-09-16"),
            question(
                15, "2026-09-07", answeringBodyId=60, answeringBodyName="Education"
            ),
        ],
        dt.date(2026, 9, 15),
        bank_holidays,
    )
    total = next(
        row
        for row in dataset.rows
        if row.department == "all"
        and row.period == "last_30_days"
        and row.type == "ordinary"
    )
    assert (total.received_count, total.answered_count, total.answered_on_time) == (
        7,
        2,
        1,
    )
    assert (total.waiting_within_allowed_period, total.waiting_overdue) == (1, 4)
    priority = next(
        row
        for row in dataset.rows
        if row.department == "all"
        and row.period == "last_30_days"
        and row.type == "priority"
    )
    assert (
        priority.received_count,
        priority.answered_count,
        priority.answered_on_time,
        priority.waiting_overdue,
    ) == (2, 1, 1, 1)
    for row in dataset.rows:
        assert (
            row.received_count
            == row.answered_count
            + row.waiting_within_allowed_period
            + row.waiting_overdue
        )
        assert row.answered_on_time <= row.answered_count
        if row.department == "all":
            departments = [
                other
                for other in dataset.rows
                if other.department_id is not None
                and other.period == row.period
                and other.type == row.type
            ]
            overdue_rows = [
                bucket
                for bucket in dataset.overdue_rows
                if bucket.period == row.period and bucket.type == row.type
            ]
            from uk_parl_written_questions.overdue import (
                OverdueSelection,
                overdue_questions,
            )

            for bucket in overdue_rows:
                for status in ("answered", "pending"):
                    details = overdue_questions(
                        dataset,
                        OverdueSelection(
                            days=30 if row.period == "last_30_days" else 90,
                            question_type=row.type,
                            status=status,
                            days_overdue=bucket.days_overdue,
                        ),
                    )
                    assert len(details) == getattr(bucket, f"{status}_count")
                    assert len({question.id for question in details}) == len(details)
            assert (
                sum(bucket.answered_count for bucket in overdue_rows)
                == row.answered_count - row.answered_on_time
            )
            assert (
                sum(bucket.pending_count for bucket in overdue_rows)
                == row.waiting_overdue
            )
            for field in [
                "received_count",
                "answered_count",
                "answered_on_time",
                "waiting_within_allowed_period",
                "waiting_overdue",
            ]:
                assert getattr(row, field) == sum(
                    getattr(other, field) for other in departments
                )
    long_total = next(
        row
        for row in dataset.rows
        if row.department == "all"
        and row.period == "last_90_days"
        and row.type == "ordinary"
    )
    assert long_total.received_count == 9


def test_deduplication_uses_last_record_and_latest_department_name(
    bank_holidays: BankHolidays,
) -> None:
    """
    Count updated questions once and group department name variants by ID.
    """
    rows = aggregate_performance(
        [
            question(1, "2026-09-07", answeringBodyName="Old name"),
            question(1, "2026-09-07", dateAnswered="2026-09-14"),
            question(2, "2026-09-08", answeringBodyName=" New name "),
        ],
        dt.date(2026, 9, 15),
        bank_holidays,
    ).rows
    department = next(
        row
        for row in rows
        if row.department_id == 1
        and row.period == "last_30_days"
        and row.type == "ordinary"
    )
    assert department.department == "New name"
    assert department.received_count == 2
    assert department.answered_count == 1


def test_working_days_exclude_weekend_and_bank_holiday() -> None:
    """
    Skip the August bank holiday and fail when calendar coverage runs out.
    """
    calendar = BankHolidays(
        source="test", first_year=2026, last_year=2026, dates={dt.date(2026, 8, 31)}
    )
    assert calendar.ordinary_target_date(dt.date(2026, 8, 25)) == dt.date(2026, 9, 1)
    with pytest.raises(ValueError, match="Update bank_holidays"):
        calendar.ordinary_target_date(dt.date(2026, 12, 31))


def test_missing_month_fails_instead_of_publishing_partial_totals(
    tmp_path: Path,
) -> None:
    """
    Require all cache files needed for the complete rolling window.
    """
    with pytest.raises(ValueError, match="Missing cached month"):
        load_recent_questions(tmp_path, dt.date(2026, 9, 15))


def test_aggregation_is_independent_of_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bank_holidays: BankHolidays
) -> None:
    """
    Assess questions with an explicit calendar even outside a repository.
    """
    monkeypatch.chdir(tmp_path)
    dataset = aggregate_performance(
        [question(1, "2026-09-14", dateForAnswer="2026-09-16")],
        dt.date(2026, 9, 15),
        bank_holidays,
    )
    assert all(row.on_time_rate is None for row in dataset.rows)
    assert not list(tmp_path.iterdir())
    assert "on_time_rate" not in dataset.model_dump_json()


def test_overdue_delays_stop_at_substantive_answer_or_assessment(
    bank_holidays: BankHolidays,
) -> None:
    """
    Use working days for late answers, pending, holding replies and both cohorts.
    """
    dataset = aggregate_performance(
        [
            question(
                1, "2026-08-24", dateForAnswer="2026-08-26", dateAnswered="2026-09-03"
            ),
            question(2, "2026-08-24", dateForAnswer="2026-08-26"),
            question(
                3,
                "2026-08-24",
                dateForAnswer="2026-08-26",
                dateAnswered="2026-09-03",
                answerIsHolding=True,
            ),
            question(
                4, "2026-08-24", dateForAnswer="2026-08-26", dateAnswered="2026-09-16"
            ),
            question(
                5, "2026-08-24", dateForAnswer="2026-08-26", dateAnswered="2026-09-02"
            ),
            question(
                6,
                "2026-08-28",
                isNamedDay=True,
                dateForAnswer="2026-08-28",
                dateAnswered="2026-08-31",
            ),
            question(7, "2026-08-28", isNamedDay=True, dateForAnswer="2026-08-28"),
            question(
                7,
                "2026-08-28",
                isNamedDay=True,
                dateForAnswer="2026-08-28",
                dateAnswered="2026-09-01",
            ),
            question(8, "2026-09-14", isNamedDay=True, dateForAnswer="2026-09-14"),
            question(9, "2026-09-14", isNamedDay=True, dateForAnswer="2026-09-15"),
            question(
                10,
                "2026-08-16",
                isNamedDay=True,
                dateForAnswer="2026-08-17",
                dateAnswered="2026-08-18",
            ),
            question(11, "2026-08-24", isWithdrawn=True),
            question(12, "2026-08-24", answeringBodyId=9),
            question(13, "2026-09-16"),
        ],
        dt.date(2026, 9, 15),
        bank_holidays,
    )
    assert dataset.overdue_day_basis == "working"
    ordinary = [
        row
        for row in dataset.overdue_rows
        if row.period == "last_30_days" and row.type == "ordinary"
    ]
    assert [
        row.model_dump(include={"days_overdue", "answered_count", "pending_count"})
        for row in ordinary
    ] == [
        {"days_overdue": 1, "answered_count": 1, "pending_count": 0},
        {"days_overdue": 9, "answered_count": 0, "pending_count": 3},
    ]
    urgent = [
        row
        for row in dataset.overdue_rows
        if row.period == "last_30_days" and row.type == "priority"
    ]
    assert [
        row.model_dump(include={"days_overdue", "answered_count", "pending_count"})
        for row in urgent
    ] == [
        {"days_overdue": 0, "answered_count": 1, "pending_count": 0},
        {"days_overdue": 1, "answered_count": 1, "pending_count": 1},
    ]
    urgent_90 = [
        row
        for row in dataset.overdue_rows
        if row.period == "last_90_days" and row.type == "priority"
    ]
    assert sum(row.answered_count for row in urgent_90) == 3
    assert sum(row.pending_count for row in urgent_90) == 1


def test_working_day_delay_checks_coverage(bank_holidays: BankHolidays) -> None:
    """
    Include the end working day, skip holidays and refuse uncovered years.
    """
    assert (
        bank_holidays.working_days_after(dt.date(2026, 8, 28), dt.date(2026, 8, 31))
        == 0
    )
    assert (
        bank_holidays.working_days_after(dt.date(2026, 8, 28), dt.date(2026, 9, 1)) == 1
    )
    with pytest.raises(ValueError, match="Update bank_holidays"):
        bank_holidays.working_days_after(dt.date(2026, 12, 31), dt.date(2027, 1, 4))


def test_saved_snapshot_includes_overdue_distribution(
    tmp_path: Path, bank_holidays: BankHolidays
) -> None:
    """
    Persist delay counts in the same snapshot served by the dashboard download.
    """
    import json

    from uk_parl_written_questions.performance import (
        PACKAGE_PATH,
        PerformanceDataset,
        create_performance_dataset,
    )

    raw = tmp_path / "data/raw"
    commons = raw / "commons"
    commons.mkdir(parents=True)
    for month in (6, 7, 8, 9):
        questions = (
            [question(1, "2026-09-07", dateAnswered="2026-09-15")] if month == 9 else []
        )
        (commons / f"2026-{month:02}.json").write_text(
            json.dumps([{"value": item.model_dump(mode="json")} for item in questions])
        )
    (raw / "bank_holidays.json").write_text(bank_holidays.model_dump_json())
    dataset = create_performance_dataset(tmp_path, dt.date(2026, 9, 15))
    restored = PerformanceDataset.model_validate_json(
        (tmp_path / PACKAGE_PATH / "performance_snapshot.json").read_text()
    )
    assert restored == dataset
    assert all(
        row.days_overdue == 1 and row.answered_count == 1
        for row in restored.overdue_rows
    )
    assert len(restored.overdue_rows) == 2


@pytest.mark.parametrize("tabled", ["2026-09-07", "2026-08-18"])
def test_ordinary_target_uses_published_answer_date(
    bank_holidays: BankHolidays, tabled: str
) -> None:
    """
    Answer-date day five is on time even when tabling was much earlier in recess.
    """
    dataset = aggregate_performance(
        [
            question(1, tabled, dateForAnswer="2026-09-09", dateAnswered="2026-09-15"),
            question(2, tabled, dateForAnswer="2026-09-09", dateAnswered="2026-09-16"),
            question(3, tabled, dateForAnswer="2026-09-09"),
        ],
        dt.date(2026, 9, 16),
        bank_holidays,
    )
    total = next(
        row
        for row in dataset.rows
        if row.department == "all"
        and row.period == "last_30_days"
        and row.type == "ordinary"
    )
    assert total.answered_on_time == 1
    assert total.waiting_overdue == 1
    bucket = next(
        row
        for row in dataset.overdue_rows
        if row.period == "last_30_days" and row.type == "ordinary"
    )
    assert bucket.days_overdue == 1
    assert bucket.answered_count == 1
    assert bucket.pending_count == 1
