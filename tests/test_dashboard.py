from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from data_common.dataset.site import create_app
from data_common.dataset.site.freezer import build_site
from data_common.dataset.site.settings import get_site_settings

from uk_parl_written_questions.holidays import BankHolidays
from uk_parl_written_questions.performance import (
    PACKAGE_PATH,
    Question,
    aggregate_performance,
)


@pytest.fixture
def dashboard_repository(tmp_path: Path, bank_holidays: BankHolidays) -> Path:
    """
    Add an assessed performance snapshot to the shared site's fixture catalogue.
    """
    root = tmp_path / "repository"
    shutil.copytree(Path("src/data_common/tests/fixtures/model_repository"), root)
    dataset = aggregate_performance(
        [
            Question(
                id=1,
                dateTabled=dt.datetime(2026, 9, 1),
                dateForAnswer=dt.datetime(2026, 9, 3),
                answeringBodyId=1,
                answeringBodyName="Zulu",
                isNamedDay=False,
            ),
            Question(
                id=2,
                dateTabled=dt.datetime(2026, 9, 14),
                dateForAnswer=dt.datetime(2026, 9, 16),
                answeringBodyId=60,
                answeringBodyName="Alpha",
                isNamedDay=False,
            ),
        ],
        dt.date(2026, 9, 15),
        bank_holidays,
    )
    output = root / PACKAGE_PATH
    output.mkdir(parents=True)
    (output / "performance_snapshot.json").write_text(dataset.model_dump_json())
    return root


def test_static_dashboard_periods_without_javascript(
    dashboard_repository: Path,
) -> None:
    """
    Freeze all real links and check HTML order without executing scripts.
    """
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    app = create_app(settings=settings)
    report = build_site(app)
    base = report.output_dir / "performance"
    assert sorted(str(path.relative_to(base)) for path in base.rglob("index.html")) == [
        "index.html",
        "overdue/index.html",
        "overdue/ordinary/pending/4/index.html",
        "overdue/ordinary/pending/all/index.html",
        "overdue/period/90/index.html",
        "overdue/period/90/ordinary/pending/4/index.html",
        "overdue/period/90/ordinary/pending/all/index.html",
        "period/90/index.html",
    ]
    overdue = BeautifulSoup((base / "index.html").read_text(), "html.parser")
    assert [cell.text for cell in overdue.select("#ordinary-departments th")] == [
        "Zulu",
        "Alpha",
    ]
    assert (
        overdue.select_one("th[aria-sort=descending]")
        .get_text(strip=True)
        .startswith("Overdue")
    )
    assert overdue.select_one(".performance-total th").text == "All departments"
    assert [heading.text for heading in overdue.select(".performance-section h2")] == [
        "Urgent (named day) questions — last 30 days",
        "Ordinary questions — last 30 days",
    ]
    assert [
        link["href"] for link in overdue.select(".performance-contents-sections a")
    ] == [
        "#urgent",
        "#ordinary",
    ]
    assert len(overdue.select(".performance-table")) == 2
    for anchor in ("urgent", "ordinary"):
        section = overdue.select_one(f"#{anchor}")
        assert section is not None
        assert len(section.select("button[data-sort][disabled]")) == 7
    assert [link["href"] for link in overdue.select("a[data-period]")] == [
        "/model/performance/",
        "/model/performance/period/90/",
    ]
    assert not overdue.select("a[data-filter-root]")
    for relative in (
        "index.html",
        "period/90/index.html",
        "overdue/index.html",
        "overdue/period/90/index.html",
    ):
        path = base / relative
        page = BeautifulSoup(path.read_text(), "html.parser")
        contents = page.select_one(
            'nav[aria-labelledby="performance-contents-heading"]'
        )
        assert contents is not None
        links = contents.select(".performance-contents-pages > li > a")
        assert [link["href"] for link in links] == [
            "/model/performance/",
            "/model/performance/period/90/",
            "/model/performance/overdue/",
            "/model/performance/overdue/period/90/",
        ]
        assert [link.get_text(strip=True) for link in links] == [
            "Department performance — last 30 days",
            "Department performance — last 90 days",
            "How overdue are questions? — last 30 days",
            "How overdue are questions? — last 90 days",
        ]
        current = contents.select('a[aria-current="page"]')
        assert len(current) == 1
        assert current[0]["href"] == "/model/performance/" + relative.removesuffix(
            "index.html"
        )
        for link in contents.select(".performance-contents-sections a"):
            assert page.select_one(link["href"]) is not None
        note = page.select_one("#methodology")
        assert note is not None
        assert "counting the date itself as day one" in note.text
        assert "Answered on time ÷ (Answered + Overdue) × 100" in note.text
        assert len(note.select("a[href^='https://']")) == 2
    assert (base / "assets/table.js").is_file()
    assert (base / "assets/table.css").is_file()
    client = app.test_client()
    assert (
        client.get("/model/performance/365/ordinary/department/asc/").status_code == 404
    )
    assert client.get("/model/performance/30/ordinary/unknown/asc/").status_code == 404
    assert (
        client.get("/model/performance/performance.json").json["as_of_date"]
        == "2026-09-15"
    )
    assert b"Written question performance" in client.get("/model/").data


def test_percentage_excludes_allowed_outstanding_questions(
    dashboard_repository: Path,
) -> None:
    """
    Display on-time counts and rates, excluding pending questions and late answers from the numerator.
    """
    from uk_parl_written_questions.performance import PerformanceDataset

    path = dashboard_repository / PACKAGE_PATH / "performance_snapshot.json"
    snapshot = PerformanceDataset.model_validate_json(path.read_text())
    for row in snapshot.rows:
        if row.type == "ordinary":
            if row.department == "Zulu":
                row.received_count, row.answered_count, row.answered_on_time = 10, 8, 6
                row.waiting_overdue = 2
            elif row.department == "Alpha":
                row.received_count, row.answered_count, row.answered_on_time = 20, 2, 2
                row.waiting_within_allowed_period = 18
            else:
                row.received_count, row.answered_count, row.answered_on_time = (
                    30,
                    10,
                    8,
                )
                row.waiting_overdue, row.waiting_within_allowed_period = 2, 18
    path.write_text(snapshot.model_dump_json())
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    client = create_app(settings=settings).test_client()
    page = BeautifulSoup(
        client.get("/model/performance/").data,
        "html.parser",
    )
    assert [cell.text for cell in page.select("#ordinary-departments th")] == [
        "Zulu",
        "Alpha",
    ]
    assert [
        cell.text for cell in page.select("#ordinary-departments td[data-order]")
    ] == ["60.0%", "100.0%"]
    assert (
        page.select_one("#ordinary-table .performance-total td[data-order]").text
        == "66.7%"
    )
    assert [
        button["data-label"]
        for button in page.select("#ordinary-table button[data-sort]")
    ] == [
        "Department",
        "Received",
        "Answered",
        "Answered on time",
        "Pending",
        "Overdue",
        "On-schedule rate (%)",
    ]
    assert [
        [cell.get_text(strip=True) for cell in row.select("th, td")]
        for row in page.select("#ordinary-departments tr")
    ] == [
        ["Zulu", "10", "8", "6", "0", "2", "60.0%"],
        ["Alpha", "20", "2", "2", "18", "0", "100.0%"],
    ]
    assert [
        cell.get_text(strip=True)
        for cell in page.select(
            "#ordinary-table .performance-total th, #ordinary-table .performance-total td"
        )
    ] == ["All departments", "30", "10", "8", "18", "2", "66.7%"]
    assert len(page.select("tbody")) == 2
    assert (
        client.get("/model/performance/performance.json").json["rows"][0][
            "answered_on_time"
        ]
        == 8
    )
    empty = BeautifulSoup(
        client.get("/model/performance/").data,
        "html.parser",
    )
    assert (
        empty.select_one("#priority-table .performance-total td[data-order]").text
        == "—"
    )


def test_rate_is_undefined_when_all_questions_are_allowed_outstanding(
    dashboard_repository: Path,
) -> None:
    """
    Show a dash for pending-only cohorts rather than zero or a negative rate.
    """
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    client = create_app(settings=settings).test_client()
    page = BeautifulSoup(client.get("/model/performance/").data, "html.parser")
    alpha = next(
        row for row in page.select("#ordinary-departments tr") if row.th.text == "Alpha"
    )
    cell = alpha.select_one("td[data-order]")
    assert cell.text == "—"
    assert cell["data-order"] == "-1"


def test_shared_blueprint_keeps_snapshots_specific_to_each_app(
    dashboard_repository: Path,
) -> None:
    """
    Register the module-level blueprint twice without sharing loaded data.
    """
    from uk_parl_written_questions.performance import PerformanceDataset

    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    first = create_app(settings=settings).test_client()
    path = dashboard_repository / PACKAGE_PATH / "performance_snapshot.json"
    snapshot = PerformanceDataset.model_validate_json(path.read_text())
    for row in snapshot.rows:
        if row.department == "Alpha":
            row.department = "Replacement department"
    path.write_text(snapshot.model_dump_json())
    second = create_app(settings=settings).test_client()

    for client, expected, excluded in [
        (first, "Alpha", "Replacement department"),
        (second, "Replacement department", "Alpha"),
    ]:
        page = client.get("/model/performance/")
        assert page.status_code == 200
        assert expected.encode() in page.data
        assert excluded.encode() not in page.data
        data = client.get("/model/performance/performance.json").json
        names = {row["department"] for row in data["rows"]}
        assert expected in names
        assert excluded not in names


def test_javascript_matches_static_pages(
    dashboard_repository: Path, bank_holidays: BankHolidays, tmp_path: Path
) -> None:
    """
    Exercise independent table sorting on both short period URLs.
    """
    import json
    import subprocess

    from uk_parl_written_questions.dashboard import create_extension
    from uk_parl_written_questions.performance import PerformanceDataset

    dataset = aggregate_performance(
        [
            Question(
                id=index,
                dateTabled=dt.datetime(2026, 9, 14 if index == 5 else 1),
                dateForAnswer=dt.datetime(2026, 9, 16 if index == 5 else 3),
                dateAnswered=dt.datetime(2026, 9, 2) if index == 0 else None,
                answeringBodyId=index + 100,
                answeringBodyName=name,
                isNamedDay=False,
            )
            for index, name in enumerate(
                ["Zulu", "alpha", "ALPHA", "Álpha", "Same", "Same"]
            )
        ],
        dt.date(2026, 9, 15),
        bank_holidays,
    )
    priority = aggregate_performance(
        [
            Question(
                id=500 + index,
                dateTabled=dt.datetime(2026, 9, 1),
                dateForAnswer=dt.datetime(2026, 9, 3),
                dateAnswered=dt.datetime(2026, 9, 2) if index == 0 else None,
                answeringBodyId=index + 100,
                answeringBodyName=name,
                isNamedDay=True,
            )
            for index, name in enumerate(
                ["Zulu", "alpha", "ALPHA", "Álpha", "Same", "Same"]
            )
        ],
        dataset.as_of_date,
        bank_holidays,
    )
    dataset.rows = [row for row in dataset.rows if row.type == "ordinary"] + [
        row for row in priority.rows if row.type == "priority"
    ]
    path = dashboard_repository / PACKAGE_PATH / "performance_snapshot.json"
    path.write_text(dataset.model_dump_json())
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    client = create_app(settings=settings).test_client()
    pages = tmp_path / "pages"
    pages.mkdir()
    manifest: dict[str, str] = {}
    for index, target in enumerate(create_extension(settings).targets):
        if target.mimetype != "text/html" or "/overdue/" in target.url:
            continue
        response = client.get(target.url)
        assert response.status_code == 200
        filename = f"{index}.html"
        (pages / filename).write_bytes(response.data)
        manifest[target.url] = filename
    (pages / "manifest.json").write_text(json.dumps(manifest))

    empty = aggregate_performance([], dataset.as_of_date, bank_holidays)
    path.write_text(empty.model_dump_json())
    empty_page = create_app(settings=settings).test_client().get("/model/performance/")
    (pages / "empty.html").write_bytes(empty_page.data)
    assert PerformanceDataset.model_validate_json(
        client.get("/model/performance/performance.json").data
    ).rows

    result = subprocess.run(
        ["node", "tests/javascript/dashboard.cjs", str(pages)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "path",
    [
        "period/365/",
        "period/30/",
        "90/",
        "30/unknown/asc/department/asc/",
        "30/department/asc/unknown/asc/",
        "30/department/asc/department/unknown/",
        "30/department/unknown/department/asc/",
    ],
)
def test_invalid_selection_returns_404(dashboard_repository: Path, path: str) -> None:
    """
    Validate each route component before selecting or sorting rows.
    """
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    assert (
        create_app(settings=settings)
        .test_client()
        .get(f"/model/performance/{path}")
        .status_code
        == 404
    )


@pytest.mark.parametrize("days", [30, 90])
def test_overdue_grid_and_period_links(dashboard_repository: Path, days: int) -> None:
    """
    Render exact delays, zero-count gaps and empty cohorts without JavaScript.
    """
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    client = create_app(settings=settings).test_client()
    suffix = "" if days == 30 else "period/90/"
    response = client.get(f"/model/performance/overdue/{suffix}")
    assert response.status_code == 200
    page = BeautifulSoup(response.data, "html.parser")
    assert [heading.text for heading in page.select(".performance-section h2")] == [
        f"Urgent (named day) questions — last {days} days",
        f"Ordinary questions — last {days} days",
    ]
    grid = page.select_one("#ordinary-overdue")
    assert [cell.text for cell in grid.select("thead th")] == [
        "Working days overdue",
        "Answered",
        "Pending",
    ]
    assert [
        [cell.text for cell in row.select("th, td")] for row in grid.select("tbody tr")
    ] == [[str(delay), "0", "1" if delay == 4 else "0"] for delay in range(1, 5)]
    assert [cell.text for cell in grid.select("tfoot td")] == ["0", "1"]
    assert "No overdue questions" in page.select_one("#priority-overdue").text
    assert [link["href"] for link in page.select("a[data-period]")] == [
        "/model/performance/overdue/",
        "/model/performance/overdue/period/90/",
    ]
    current_links = page.select('.performance-contents a[aria-current="page"]')
    assert len(current_links) == 1
    assert current_links[0]["href"] == f"/model/performance/overdue/{suffix}"
    data = client.get("/model/performance/performance.json").json
    assert data["overdue_day_basis"] == "working"
    assert (
        data["ordinary_target_basis"] == "date_for_answer_inclusive_five_working_days"
    )
    assert any(
        row["days_overdue"] == 4 and row["pending_count"] == 1
        for row in data["overdue_rows"]
    )
    home = BeautifulSoup(client.get("/model/").data, "html.parser")
    tool_links = home.select('ul[aria-labelledby="tools-heading"] a')
    assert [link["href"] for link in tool_links] == ["/model/performance/"]
    assert tool_links[0].get_text(strip=True) == "Written question performance"


@pytest.mark.parametrize(
    "missing_field", ["overdue_rows", "ordinary_target_basis", "overdue_questions"]
)
def test_old_snapshot_requires_rebuild(
    dashboard_repository: Path, missing_field: str
) -> None:
    """
    Refuse an old snapshot rather than showing missing delay data as zero.
    """
    import json

    path = dashboard_repository / PACKAGE_PATH / "performance_snapshot.json"
    snapshot = json.loads(path.read_text())
    del snapshot[missing_field]
    path.write_text(json.dumps(snapshot))
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    with pytest.raises(ValueError, match="snapshot needs rebuilding"):
        create_app(settings=settings)


def test_weekend_only_delay_is_visible(
    dashboard_repository: Path, bank_holidays: BankHolidays
) -> None:
    """
    Preserve overdue questions with zero elapsed working days in the rendered grid.
    """
    dataset = aggregate_performance(
        [
            Question(
                id=1,
                dateTabled=dt.datetime(2026, 8, 28),
                dateForAnswer=dt.datetime(2026, 8, 28),
                dateAnswered=dt.datetime(2026, 8, 31),
                answeringBodyId=1,
                answeringBodyName="Home Office",
                isNamedDay=True,
            ),
            Question(
                id=2,
                dateTabled=dt.datetime(2026, 8, 28),
                dateForAnswer=dt.datetime(2026, 8, 28),
                answeringBodyId=1,
                answeringBodyName="Home Office",
                isNamedDay=True,
            ),
        ],
        dt.date(2026, 8, 31),
        bank_holidays,
    )
    (dashboard_repository / PACKAGE_PATH / "performance_snapshot.json").write_text(
        dataset.model_dump_json()
    )
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    page = BeautifulSoup(
        create_app(settings=settings)
        .test_client()
        .get("/model/performance/overdue/")
        .data,
        "html.parser",
    )
    assert [
        cell.text
        for cell in page.select(
            "#priority-overdue tbody tr th, #priority-overdue tbody tr td"
        )
    ] == ["Less than 1", "1", "1"]
    assert "no working day has elapsed" in page.text


@pytest.mark.parametrize("days", [30, 90])
def test_overdue_count_links_reconcile_with_saved_questions(
    dashboard_repository: Path, bank_holidays: BankHolidays, days: int
) -> None:
    """
    Link every nonzero cell and total to exactly its saved questions, without raw data.
    """
    records = [
        {
            "id": 1,
            "dateAnswered": "2026-09-10",
            "questionText": "To ask about <script>alert(1)</script> & funding.",
        },
        {"id": 2},
        {"id": 3, "dateAnswered": "2026-09-10", "answerIsHolding": True},
        {
            "id": 4,
            "isNamedDay": True,
            "dateForAnswer": "2026-09-10",
            "dateAnswered": "2026-09-11",
        },
        {
            "id": 5,
            "isNamedDay": True,
            "dateTabled": "2026-08-28",
            "dateForAnswer": "2026-08-28",
            "dateAnswered": "2026-08-31",
        },
        {"id": 6, "dateTabled": "2026-08-16", "dateAnswered": "2026-09-10"},
        {"id": 7, "isNamedDay": True, "dateForAnswer": "2026-09-16"},
        {"id": 8, "isWithdrawn": True},
    ]
    dataset = aggregate_performance(
        [
            Question.model_validate(
                {
                    "uin": str(1000 + record["id"]),
                    "questionText": "To ask about public services.",
                    "dateTabled": "2026-09-01",
                    "dateForAnswer": "2026-09-03",
                    "answeringBodyId": 1,
                    "answeringBodyName": "Home Office",
                    "isNamedDay": False,
                    **record,
                }
            )
            for record in records
        ],
        dt.date(2026, 9, 15),
        bank_holidays,
    )
    (dashboard_repository / PACKAGE_PATH / "performance_snapshot.json").write_text(
        dataset.model_dump_json()
    )
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    app = create_app(settings=settings)
    client = app.test_client()
    root = "/model/performance/overdue/" + ("period/90/" if days == 90 else "")
    grid = BeautifulSoup(client.get(root).data, "html.parser")
    for cell in grid.select(".overdue-grid tbody td, .overdue-grid tfoot td"):
        count = int(cell.get_text(strip=True))
        link = cell.select_one("a")
        if not count:
            assert link is None
            continue
        assert link is not None
        response = client.get(link["href"])
        assert response.status_code == 200
        page = BeautifulSoup(response.data, "html.parser")
        rows = page.select(".question-list tbody tr")
        assert len(rows) == count
        assert f"last {days} days" in page.text
        assert "2026-09-15" in page.text
        for row in rows:
            assert row.select_one("a")["href"].startswith(
                "https://questions-statements.parliament.uk/written-questions/detail/"
            )
        back = page.find("a", string="Back to the overdue grid")
        assert back["href"].startswith(root + "#")
    answered = BeautifulSoup(
        client.get(root + "ordinary/answered/1/").data, "html.parser"
    )
    assert [row["data-question-id"] for row in answered.select("tbody tr")] == (
        ["1"] if days == 30 else ["6", "1"]
    )
    first = answered.select_one('tr[data-question-id="1"]')
    assert (
        first.select_one("a")["href"]
        == "https://questions-statements.parliament.uk/written-questions/detail/2026-09-01/1001/"
    )
    assert "2026-09-09" in first.text
    assert "2026-09-10" in first.text
    assert first.select_one("script") is None
    assert "<script>alert(1)</script>" in first.text
    pending = BeautifulSoup(
        client.get(root + "ordinary/pending/all/").data, "html.parser"
    )
    assert [row["data-question-id"] for row in pending.select("tbody tr")] == ["2", "3"]
    assert "Answered" not in [cell.text for cell in pending.select("thead th")]
    zero = BeautifulSoup(client.get(root + "priority/answered/0/").data, "html.parser")
    assert any(
        "less than 1 working day overdue" in heading.text
        for heading in zero.select("h1")
    )
    assert zero.select_one("tbody tr")["data-question-id"] == "5"
    # Freeze the same pages and verify every grid link has a real output file.
    report = build_site(app)
    for link in grid.select(".overdue-grid a"):
        relative = str(link["href"]).removeprefix("/model/")
        assert (report.output_dir / relative / "index.html").is_file()


@pytest.mark.parametrize(
    "path",
    [
        "ordinary/pending/999/",
        "ordinary/answered/all/",
        "ordinary/pending/-1/",
        "unknown/pending/4/",
        "ordinary/unknown/4/",
        "period/30/ordinary/pending/4/",
        "period/365/ordinary/pending/4/",
    ],
)
def test_invalid_or_empty_overdue_details_return_404(
    dashboard_repository: Path, path: str
) -> None:
    """
    Do not serve empty lists or unsupported filters that have no static target.
    """
    settings = get_site_settings(repo_root=dashboard_repository).model_copy(
        update={"extensions": ("uk_parl_written_questions.dashboard:create_extension",)}
    )
    client = create_app(settings=settings).test_client()
    assert client.get("/model/performance/overdue/" + path).status_code == 404
