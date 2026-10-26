from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, get_args
from urllib.parse import quote

import pandas as pd
from pydantic import BaseModel, Field

from .holidays import BankHolidays, load_bank_holidays

QuestionType = Literal["ordinary", "priority"]
AnswerStatus = Literal["answered", "pending"]
PeriodDays = Literal[30, 90]
PERIODS: tuple[PeriodDays, ...] = get_args(PeriodDays)
QUESTION_TYPES: tuple[QuestionType, ...] = get_args(QuestionType)
NON_GOVERNMENT_BODY_IDS = frozenset({9, 18, 24, 36, 90, 91, 213})
PACKAGE_PATH = Path("data/packages/commons_written_questions_performance")


class Question(BaseModel):
    """
    Read the source fields used to assess substantive answers.
    """

    id: int
    uin: str = ""
    questionText: str = ""
    dateTabled: dt.datetime
    dateForAnswer: dt.datetime
    dateAnswered: dt.datetime | None = None
    answeringBodyId: int
    answeringBodyName: str
    isNamedDay: bool
    isWithdrawn: bool = False
    answerIsHolding: bool | None = None

    def substantive_answer_date(self, as_of_date: dt.date) -> dt.date | None:
        """
        Return an answer recorded by the assessment date, excluding holding replies.
        """
        answered = self.dateAnswered.date() if self.dateAnswered else None
        if answered and answered <= as_of_date and not self.answerIsHolding:
            return answered
        return None


class PerformanceRow(BaseModel):
    """
    Summarise a tabling cohort at an explicit assessment date.
    """

    period_type: Literal["rolling"] = "rolling"
    period: str
    period_start: dt.date
    period_end: dt.date
    as_of_date: dt.date
    department_id: int | None
    department: str
    type: QuestionType
    received_count: int = 0
    answered_count: int = 0
    answered_on_time: int = 0
    waiting_within_allowed_period: int = 0
    waiting_overdue: int = 0

    @property
    def on_time_rate(self) -> float | None:
        """
        Return the assessed percentage, or None when every question is pending.
        """
        assessed = self.received_count - self.waiting_within_allowed_period
        return 100 * self.answered_on_time / assessed if assessed else None

    def include(self, question: Question, deadline: dt.date) -> None:
        """
        Add one question to mutually exclusive answer-status counts.
        """
        self.received_count += 1
        answered = question.substantive_answer_date(self.as_of_date)
        if answered:
            self.answered_count += 1
            self.answered_on_time += int(answered <= deadline)
        elif deadline < self.as_of_date:
            self.waiting_overdue += 1
        else:
            self.waiting_within_allowed_period += 1


class OverdueRow(BaseModel):
    """
    Count late answers and outstanding questions at an exact working-day delay.

    Answered delays stop at the substantive answer; pending delays stop at the
    dataset assessment date. On-time answers and allowed pending are excluded.
    """

    period: str
    type: QuestionType
    days_overdue: int = Field(ge=0)
    answered_count: int = Field(default=0, ge=0)
    pending_count: int = Field(default=0, ge=0)


class OverdueQuestion(BaseModel):
    """
    Preserve one overdue question and its assessed dates for linked detail pages.
    """

    id: int
    uin: str
    text: str
    type: QuestionType
    department: str
    tabled: dt.date
    target: dt.date
    answered: dt.date | None
    days_overdue: int = Field(ge=0)

    @property
    def status(self) -> AnswerStatus:
        """
        Distinguish substantive answers from questions pending at assessment.
        """
        return "answered" if self.answered is not None else "pending"

    @property
    def parliament_url(self) -> str | None:
        """
        Link to the published question when its parliamentary number is available.
        """
        if not self.uin:
            return None
        return (
            "https://questions-statements.parliament.uk/written-questions/detail/"
            f"{self.tabled.isoformat()}/{quote(self.uin, safe='')}/"
        )


class PerformanceDataset(BaseModel):
    """
    Persist aggregate rows and source freshness alongside the assessment date.
    """

    as_of_date: dt.date
    source_refreshed_at: dt.datetime | None = None
    rows: list[PerformanceRow] = Field(default_factory=list)
    overdue_rows: list[OverdueRow]
    overdue_questions: list[OverdueQuestion]
    overdue_day_basis: Literal["working"] = "working"
    ordinary_target_basis: Literal["date_for_answer_inclusive_five_working_days"]


def aggregate_performance(
    questions: Iterable[Question],
    as_of_date: dt.date,
    holidays: BankHolidays,
) -> PerformanceDataset:
    """
    Build 30- and 90-day cohorts; the last supplied record wins for duplicate IDs.

    Government bodies retain their source IDs. Non-government answering bodies
    and withdrawn questions are excluded from departmental and all totals.
    """
    unique = {question.id: question for question in questions}
    start = as_of_date - dt.timedelta(days=max(PERIODS) - 1)
    eligible = sorted(
        (
            question
            for question in unique.values()
            if start <= question.dateTabled.date() <= as_of_date
            and not question.isWithdrawn
            and question.answeringBodyId not in NON_GOVERNMENT_BODY_IDS
        ),
        key=lambda question: (question.dateTabled, question.id),
    )
    departments = {
        question.answeringBodyId: question.answeringBodyName.strip()
        for question in eligible
    }
    dataset = PerformanceDataset(
        as_of_date=as_of_date,
        overdue_rows=[],
        overdue_questions=[],
        ordinary_target_basis="date_for_answer_inclusive_five_working_days",
    )
    for days in PERIODS:
        period_start = as_of_date - dt.timedelta(days=days - 1)
        for question_type in QUESTION_TYPES:
            overdue: dict[int, OverdueRow] = {}
            rows = {
                department_id: PerformanceRow(
                    period=f"last_{days}_days",
                    period_start=period_start,
                    period_end=as_of_date,
                    as_of_date=as_of_date,
                    department_id=department_id,
                    department=department,
                    type=question_type,
                )
                for department_id, department in departments.items()
            }
            total = PerformanceRow(
                period=f"last_{days}_days",
                period_start=period_start,
                period_end=as_of_date,
                as_of_date=as_of_date,
                department_id=None,
                department="all",
                type=question_type,
            )
            for question in eligible:
                if question.dateTabled.date() < period_start:
                    continue
                if question.isNamedDay != (question_type == "priority"):
                    continue
                deadline = (
                    question.dateForAnswer.date()
                    if question.isNamedDay
                    else holidays.ordinary_target_date(question.dateForAnswer.date())
                )
                rows[question.answeringBodyId].include(question, deadline)
                total.include(question, deadline)
                answered = question.substantive_answer_date(as_of_date)
                end_date = answered or as_of_date
                if end_date > deadline:
                    delay = holidays.working_days_after(deadline, end_date)
                    if days == max(PERIODS):
                        dataset.overdue_questions.append(
                            OverdueQuestion(
                                id=question.id,
                                uin=question.uin,
                                text=question.questionText,
                                type=question_type,
                                department=departments[question.answeringBodyId],
                                tabled=question.dateTabled.date(),
                                target=deadline,
                                answered=answered,
                                days_overdue=delay,
                            )
                        )
                    bucket = overdue.setdefault(
                        delay,
                        OverdueRow(
                            period=total.period, type=question_type, days_overdue=delay
                        ),
                    )
                    if answered:
                        bucket.answered_count += 1
                    else:
                        bucket.pending_count += 1
            dataset.overdue_rows.extend(overdue[delay] for delay in sorted(overdue))
            dataset.rows.extend(
                [total, *sorted(rows.values(), key=lambda row: row.department)]
            )
    return dataset


def load_recent_questions(repo_root: Path, as_of_date: dt.date) -> list[Question]:
    """
    Read cached months covering the rolling windows and require complete coverage.
    """
    start = as_of_date - dt.timedelta(days=max(PERIODS) - 1)
    month = start.replace(day=1)
    questions: list[Question] = []
    while month <= as_of_date:
        path = repo_root / "data/raw/commons" / f"{month:%Y-%m}.json"
        if not path.exists():
            raise ValueError(f"Missing cached month {path}; run project fetch first")
        questions.extend(
            Question.model_validate(item["value"])
            for item in json.loads(path.read_text())
        )
        month = (month.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return questions


def create_performance_dataset(
    repo_root: Path | None = None,
    as_of_date: dt.date | None = None,
) -> PerformanceDataset:
    """
    Build publishable aggregates from the existing cache, without text enrichment.
    """
    root = repo_root or Path.cwd()
    assessment_date = as_of_date or dt.datetime.now(dt.timezone.utc).date()
    dataset = aggregate_performance(
        load_recent_questions(root, assessment_date),
        assessment_date,
        load_bank_holidays(root),
    )
    refresh_path = root / "data/raw/commons_refresh.json"
    if refresh_path.exists():
        dataset.source_refreshed_at = dt.datetime.fromisoformat(
            json.loads(refresh_path.read_text())["refreshed_at"]
        )
    output = root / PACKAGE_PATH
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row.model_dump(mode="json") for row in dataset.rows]).to_parquet(
        output / "performance.parquet",
        index=False,
    )
    (output / "performance_snapshot.json").write_text(
        dataset.model_dump_json(indent=2) + "\n"
    )
    return dataset
