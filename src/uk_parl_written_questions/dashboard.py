from __future__ import annotations

from pathlib import Path
from typing import Literal, NamedTuple

from data_common.dataset.site.extensions import SiteExtension
from data_common.dataset.site.models import BuildTarget
from data_common.dataset.site.settings import NavigationItem, SiteSettings
from flask import Blueprint, Response, abort, current_app, render_template
from flask.sansio.blueprints import BlueprintSetupState
from pydantic import BaseModel, ConfigDict, ValidationError

from .overdue import (
    OverdueSelection,
    overdue_questions,
    overdue_selections,
    overdue_tables,
)
from .performance import (
    PACKAGE_PATH,
    PERIODS,
    AnswerStatus,
    PerformanceDataset,
    PerformanceRow,
    PeriodDays,
    QuestionType,
)

SortDirection = Literal["asc", "desc"]
SortName = Literal[
    "department",
    "received_count",
    "answered_count",
    "answered_on_time",
    "on_time_rate",
    "waiting_within_allowed_period",
    "waiting_overdue",
]


class SortColumn(NamedTuple):
    """
    Describe an accessible table heading and its default sort direction.
    """

    name: SortName
    label: str
    direction: SortDirection = "desc"


COLUMNS = (
    SortColumn("department", "Department", "asc"),
    SortColumn("received_count", "Received"),
    SortColumn("answered_count", "Answered"),
    SortColumn("answered_on_time", "Answered on time"),
    SortColumn("waiting_within_allowed_period", "Pending"),
    SortColumn("waiting_overdue", "Overdue"),
    SortColumn("on_time_rate", "On-schedule rate (%)"),
)


class TableOrder(BaseModel):
    """
    Describe the independent sort order of one question table.
    """

    model_config = ConfigDict(frozen=True)

    sort: SortName = "waiting_overdue"
    direction: SortDirection = "desc"

    def for_column(self, column: SortColumn) -> TableOrder:
        """
        Reverse the current column, or use a new column's default direction.
        """
        direction = column.direction
        if self.sort == column.name:
            direction = "asc" if self.direction == "desc" else "desc"
        return TableOrder(sort=column.name, direction=direction)


class DashboardSelection(BaseModel):
    """
    Identify the selected period and its short static URL.
    """

    model_config = ConfigDict(frozen=True)

    days: PeriodDays = 30
    view: Literal["departments", "overdue"] = "departments"

    @property
    def path(self) -> str:
        """
        Return the default page for 30 days and /period/90/ for 90 days.
        """
        root = "performance/overdue/" if self.view == "overdue" else "performance/"
        return root if self.days == 30 else f"{root}period/{self.days}/"

    def for_period(self, days: PeriodDays) -> DashboardSelection:
        """
        Select the other reporting period.
        """
        return self.model_copy(update={"days": days})

    def for_view(self, view: Literal["departments", "overdue"]) -> DashboardSelection:
        """
        Switch dashboard views while retaining the selected period.
        """
        return self.model_copy(update={"view": view})


class DepartmentRow(NamedTuple):
    """
    Pair counts with a unique alphabetical rank shared with the browser.
    """

    row: PerformanceRow
    rank: int


def sorted_departments(
    rows: list[PerformanceRow], selection: TableOrder
) -> list[DepartmentRow]:
    """
    Sort case-insensitively, retaining alphabetical ties for numeric columns.

    Case, then department ID, breaks equal-name ties deterministically. The
    browser sorts by the same rank instead of its own text collation rules.
    """
    alphabetical = sorted(
        rows,
        key=lambda row: (row.department.casefold(), row.department, row.department_id),
    )
    ranked = [DepartmentRow(row, rank) for rank, row in enumerate(alphabetical)]
    descending = selection.direction == "desc"
    if selection.sort == "department":
        return list(reversed(ranked)) if descending else ranked
    if selection.sort == "on_time_rate":
        return sorted(
            ranked,
            key=lambda entry: (
                entry.row.on_time_rate is not None,
                entry.row.on_time_rate or 0,
            ),
            reverse=descending,
        )
    return sorted(
        ranked,
        key=lambda entry: getattr(entry.row, selection.sort),
        reverse=descending,
    )


class DashboardTable(NamedTuple):
    """
    Supply the heading, explanation and counts for one question type.
    """

    question_type: QuestionType
    anchor: str
    title: str
    description: str
    order: TableOrder
    total: PerformanceRow
    rows: list[DepartmentRow]


def dashboard_tables(
    dataset: PerformanceDataset, selection: DashboardSelection
) -> list[DashboardTable]:
    """
    Present urgent questions first, followed by ordinary questions.
    """
    tables: list[DashboardTable] = []
    for question_type in ("priority", "ordinary"):
        selected = [
            row
            for row in dataset.rows
            if row.period == f"last_{selection.days}_days" and row.type == question_type
        ]
        order = TableOrder()
        urgent = question_type == "priority"
        tables.append(
            DashboardTable(
                question_type=question_type,
                anchor="urgent" if urgent else "ordinary",
                title="Urgent (named day) questions"
                if urgent
                else "Ordinary questions",
                description=(
                    "Priority written questions with a specified date for an answer. "
                    "Answers are on schedule when received by that named date."
                    if urgent
                    else "Answers are assessed against a five-working-day target, counting "
                    "the published date for answer as day one and excluding weekends "
                    "and England and Wales bank holidays."
                ),
                order=order,
                total=next(row for row in selected if row.department_id is None),
                rows=sorted_departments(
                    [row for row in selected if row.department_id is not None], order
                ),
            )
        )
    return tables


blueprint = Blueprint(
    "performance",
    __name__,
    template_folder="templates",
    static_folder="static/performance",
    static_url_path="/performance/assets",
)


@blueprint.record_once
def load_dataset(state: BlueprintSetupState) -> None:
    """
    Load the snapshot once for each app that registers this blueprint.
    """
    settings: SiteSettings = state.app.config["SITE_SETTINGS"]
    state.app.extensions["performance_dataset"] = read_dataset(settings)


def read_dataset(settings: SiteSettings) -> PerformanceDataset:
    """
    Read the same validated snapshot for route registration and page rendering.
    """
    snapshot = settings.repo_root / PACKAGE_PATH / "performance_snapshot.json"
    if not snapshot.exists():
        raise ValueError(
            "Performance snapshot missing; run dataset build --slug "
            "commons_written_questions_performance before building or serving the site"
        )
    try:
        dataset = PerformanceDataset.model_validate_json(snapshot.read_text())
    except ValidationError as error:
        raise ValueError(
            "Performance snapshot needs rebuilding; run dataset build --slug "
            "commons_written_questions_performance before building or serving the site"
        ) from error
    return dataset


def get_dataset() -> PerformanceDataset:
    """
    Return the snapshot belonging to the app handling the current request.
    """
    return current_app.extensions["performance_dataset"]


@blueprint.get("/performance/", defaults={"days": 30})
@blueprint.get("/performance/period/90/", defaults={"days": 90}, strict_slashes=False)
def index(days: PeriodDays) -> str:
    """
    Render both question types; interactive sorting never changes the URL.
    """
    selection = DashboardSelection(days=days)
    dataset = get_dataset()
    return render_template(
        "performance/index.html",
        dataset=dataset,
        tables=dashboard_tables(dataset, selection),
        columns=COLUMNS,
        selection=selection,
        periods=PERIODS,
    )


@blueprint.get("/performance/overdue/", defaults={"days": 30})
@blueprint.get(
    "/performance/overdue/period/90/", defaults={"days": 90}, strict_slashes=False
)
def overdue(days: PeriodDays) -> str:
    """
    Compare completed and outstanding delays across both question types.
    """
    selection = DashboardSelection(days=days, view="overdue")
    dataset = get_dataset()
    return render_template(
        "performance/overdue.html",
        dataset=dataset,
        tables=overdue_tables(dataset, days),
        selection=selection,
        periods=PERIODS,
    )


@blueprint.get(
    "/performance/overdue/<any(ordinary,priority):question_type>/<any(answered,pending):status>/<int:delay>/",
    defaults={"days": 30},
)
@blueprint.get(
    "/performance/overdue/period/90/<any(ordinary,priority):question_type>/<any(answered,pending):status>/<int:delay>/",
    defaults={"days": 90},
)
@blueprint.get(
    "/performance/overdue/<any(ordinary,priority):question_type>/<any(answered,pending):status>/all/",
    defaults={"days": 30, "delay": None},
)
@blueprint.get(
    "/performance/overdue/period/90/<any(ordinary,priority):question_type>/<any(answered,pending):status>/all/",
    defaults={"days": 90, "delay": None},
)
def overdue_detail(
    days: PeriodDays,
    question_type: QuestionType,
    status: AnswerStatus,
    delay: int | None,
) -> str:
    """
    Show the saved questions behind a nonzero overdue cell or column total.
    """
    selection = OverdueSelection(
        days=days, question_type=question_type, status=status, days_overdue=delay
    )
    dataset = get_dataset()
    questions = overdue_questions(dataset, selection)
    if not questions:
        abort(404)
    return render_template(
        "performance/questions.html",
        dataset=dataset,
        selection=selection,
        questions=questions,
    )


@blueprint.get("/performance/performance.json")
def data() -> Response:
    """
    Offer the exact assessed snapshot used by the table as a download.
    """
    return Response(
        get_dataset().model_dump_json(indent=2), mimetype="application/json"
    )


def create_extension(settings: SiteSettings) -> SiteExtension:
    """
    Configure dashboard build targets and navigation for the shared blueprint.
    """
    targets = [
        BuildTarget(settings.site_path("performance/"), Path("performance/index.html")),
        BuildTarget(
            settings.site_path("performance/performance.json"),
            Path("performance/performance.json"),
            "application/json",
        ),
    ]
    targets.append(
        BuildTarget(
            settings.site_path("performance/period/90/"),
            Path("performance/period/90/index.html"),
        )
    )
    for days in PERIODS:
        path = DashboardSelection(days=days, view="overdue").path
        targets.append(BuildTarget(settings.site_path(path), Path(path) / "index.html"))
    for selection in overdue_selections(read_dataset(settings)):
        targets.append(
            BuildTarget(
                settings.site_path(selection.path), Path(selection.path) / "index.html"
            )
        )
    return SiteExtension(
        blueprint=blueprint,
        targets=targets,
        navigation=[
            NavigationItem(
                title="Written question performance",
                url=settings.site_path("performance/"),
            ),
        ],
    )
