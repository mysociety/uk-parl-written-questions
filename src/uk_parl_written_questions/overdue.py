from __future__ import annotations

import datetime as dt
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from .performance import (
    PERIODS,
    AnswerStatus,
    OverdueQuestion,
    OverdueRow,
    PerformanceDataset,
    PeriodDays,
    QuestionType,
)


class OverdueSelection(BaseModel):
    """
    Identify a shareable question list within an overdue grid.
    """

    model_config = ConfigDict(frozen=True)

    days: PeriodDays
    question_type: QuestionType
    status: AnswerStatus
    days_overdue: int | None = Field(default=None, ge=0)

    @property
    def grid_path(self) -> str:
        """
        Return the grid for the selected tabling period.
        """
        root = "performance/overdue/"
        return root if self.days == 30 else f"{root}period/{self.days}/"

    @property
    def path(self) -> str:
        """
        Use an exact delay, including zero, or all delays for a column total.
        """
        delay = "all" if self.days_overdue is None else str(self.days_overdue)
        return f"{self.grid_path}{self.question_type}/{self.status}/{delay}/"

    @property
    def anchor(self) -> str:
        """
        Return to the relevant question-type section of the grid.
        """
        return "urgent" if self.question_type == "priority" else "ordinary"

    @property
    def title(self) -> str:
        """
        Describe the question type and selected working-day delay.
        """
        label = (
            "Urgent (named day) questions"
            if self.question_type == "priority"
            else "Ordinary questions"
        )
        if self.days_overdue is None:
            delay = "all overdue questions"
        elif self.days_overdue == 0:
            delay = "less than 1 working day overdue"
        else:
            unit = "day" if self.days_overdue == 1 else "days"
            delay = f"{self.days_overdue} working {unit} overdue"
        return f"{label} — {delay}"


def overdue_questions(
    dataset: PerformanceDataset, selection: OverdueSelection
) -> list[OverdueQuestion]:
    """
    Select saved question details without fetching or reassessing their status.
    """
    start = dataset.as_of_date - dt.timedelta(days=selection.days - 1)
    return sorted(
        (
            question
            for question in dataset.overdue_questions
            if start <= question.tabled <= dataset.as_of_date
            and question.type == selection.question_type
            and question.status == selection.status
            and (
                selection.days_overdue is None
                or question.days_overdue == selection.days_overdue
            )
        ),
        key=lambda question: (
            -question.days_overdue,
            question.department.casefold(),
            question.tabled,
            question.id,
        ),
    )


def overdue_selections(dataset: PerformanceDataset) -> list[OverdueSelection]:
    """
    Enumerate only populated cells and totals for static detail pages.
    """
    selections: set[OverdueSelection] = set()
    for days in PERIODS:
        for row in dataset.overdue_rows:
            if row.period != f"last_{days}_days":
                continue
            statuses: tuple[AnswerStatus, ...] = ("answered", "pending")
            for status in statuses:
                count = (
                    row.answered_count if status == "answered" else row.pending_count
                )
                if count:
                    selections.add(
                        OverdueSelection(
                            days=days,
                            question_type=row.type,
                            status=status,
                            days_overdue=row.days_overdue,
                        )
                    )
                    selections.add(
                        OverdueSelection(
                            days=days, question_type=row.type, status=status
                        )
                    )
    return sorted(selections, key=lambda selection: selection.path)


class OverdueTable(NamedTuple):
    """
    Present a complete day-by-day grid with totals for one question type.
    """

    days: PeriodDays
    question_type: QuestionType
    anchor: str
    title: str
    period_start: dt.date
    period_end: dt.date
    rows: list[OverdueRow]
    answered_count: int
    pending_count: int

    def detail_path(self, status: AnswerStatus, days_overdue: int | None = None) -> str:
        """
        Link a count to the matching question list.
        """
        return OverdueSelection(
            days=self.days,
            question_type=self.question_type,
            status=status,
            days_overdue=days_overdue,
        ).path


def overdue_tables(dataset: PerformanceDataset, days: PeriodDays) -> list[OverdueTable]:
    """
    Fill gaps between observed delays so missing days display as zero counts.
    """
    tables: list[OverdueTable] = []
    question_types: tuple[QuestionType, ...] = ("priority", "ordinary")
    for question_type in question_types:
        period = f"last_{days}_days"
        observed = {
            row.days_overdue: row
            for row in dataset.overdue_rows
            if row.period == period and row.type == question_type
        }
        rows = [
            observed.get(delay)
            or OverdueRow(period=period, type=question_type, days_overdue=delay)
            for delay in range(0 if 0 in observed else 1, max(observed, default=0) + 1)
        ]
        urgent = question_type == "priority"
        tables.append(
            OverdueTable(
                days=days,
                question_type=question_type,
                anchor="urgent" if urgent else "ordinary",
                title="Urgent (named day) questions"
                if urgent
                else "Ordinary questions",
                period_start=dataset.as_of_date - dt.timedelta(days=days - 1),
                period_end=dataset.as_of_date,
                rows=rows,
                answered_count=sum(row.answered_count for row in rows),
                pending_count=sum(row.pending_count for row in rows),
            )
        )
    return tables
