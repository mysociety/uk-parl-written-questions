
# uk-parl-written-questions

[![badge](https://mybinder.org/badge.svg)](https://mybinder.org/v2/gh/mysociety/uk-parl-written-questions/HEAD)

Dataset view of questions

This repository is available online at https://github.com/mysociety/uk-parl-written-questions

If Github Pages are enabled, the URL is: https://mysociety.github.io/uk-parl-written-questions/

## Data Build Process

To avoid GitHub's repository size limits, this project uses a two-stage data storage approach:

- **Raw data**: Monthly JSON files are stored in `data/raw/commons/` and committed to git for efficient caching
- **Processed datasets**: Large parquet files (`written_questions.parquet` and `written_questions_interests.parquet`) are generated during the build process and not committed to git

### Local Development

To build the datasets locally:

```bash
# Fetch latest data (updates recent months)
python -m src.uk_parl_written_questions fetch

# Enrich truncated text (optional standalone step — also runs inside `create`)
python -m src.uk_parl_written_questions enrich

# Generate parquet files from raw data
python -m src.uk_parl_written_questions create
```

The generated parquet files will be created in:
- `data/packages/commons_written_questions/written_questions.parquet`
- `data/packages/commons_written_questions_interests/written_questions_interests.parquet`

### Local publication

From a fresh checkout, build the datasets before publishing. The generated Parquet
files are not committed to git, and publishing without them fails with
`ValueError: No objects to concatenate` when creating the composite downloads.

```bash
uv run dataset build --all
uv run dataset publish --all
uv run dataset site build
```

This generates the downloads in `data/packages/_published/` and the website in
`_site/`. These commands build local output; deployment is handled by GitHub Actions.
`--all` selects every dataset for a subcommand: `uv run dataset --all` alone is
not a valid command.

### Long-form text enrichment

The bulk Parliament API clips `questionText` and `answerText` at 255 characters. After loading
raw data, the pipeline detects any field at exactly 255 characters and fetches the full text
from the individual question endpoint:

```
https://questions-statements-api.parliament.uk/api/writtenquestions/questions/{id}
```

Results are cached in `data/raw/longform_cache` (a local SQLite file, not committed to git) so
that subsequent runs serve from cache rather than re-fetching. Entries with an empty
`answer_text` (question not yet answered at time of last fetch) are re-fetched on the next run
in case an answer has since been added.

Run `python -m src.uk_parl_written_questions enrich` as a standalone step to perform a
historical catch-up before generating the parquet files. The `create` command runs enrichment
automatically.

### Automated Build

The GitHub Actions workflow automatically:
1. Fetches the latest data
2. Generates the parquet files (including long-form enrichment)
3. Builds and publishes the website

Instructions on using the features of this notebook (data publishing, notebook rendering, Github Pages) are available in [https://github.com/mysociety/data_common/blob/main/data-repo-readme.md](Data Common readme file).
## Rolling department performance

The dashboard covers questions tabled in the last **30 or 90 calendar days**,
including the assessment date. Urgent (priority / named day) questions appear first, followed by ordinary
questions on the same page, with headings, deadline explanations and jump links.
The selected period applies to both tables: `/performance/` shows 30 days and
`/performance/period/90/` shows 90 days. Both pages display complete tables without
JavaScript. Optional DataTables enhancement adds independent department search
and sorting within each table, without changing the URL. Reloading or changing
period resets the sorts to overdue descending. Department sorting ignores case
and uses the same alphabetical rank as the static table for numeric ties.
DataTables 3.0.4 is loaded from its CDN and requires no jQuery.
The on-schedule rate is
answered on time divided by received minus waiting within the allowed period,
displayed as a percentage to one decimal place. Late answers and overdue unanswered
questions count against the rate; allowed outstanding questions are excluded. A
dash means there are no answered or overdue questions to assess; sorting uses the unrounded rate. Downloads retain the count. The all-departments total stays above
the sorted department rows.

Build from the existing monthly cache without fetching or enriching question text:

```bash
uv run dataset build --slug commons_written_questions_performance
uv run dataset publish --slug commons_written_questions_performance
uv run dataset site build
# Or preview all site pages locally:
uv run dataset site serve
```

The dashboard is at `/uk-parl-written-questions/performance/`. The existing
`dataset build --all` workflow also builds the performance package. Run
`project fetch` first to refresh source answers; future refreshes record their UTC
completion time in `data/raw/commons_refresh.json`. Older caches omit the refresh timestamp. The dashboard uses the saved assessment
date until the performance package is rebuilt.

### How overdue?

`/performance/overdue/` shows questions tabled in the last 30 days;
`/performance/overdue/period/90/` shows the last 90 days. Both views include urgent
(named day) questions first, followed by ordinary questions, with section links.
The website header and homepage Tools list have one Written question performance
entry. A traditional contents list links to all four dashboard pages, labels the
current page, and nests its question-section and methodology links beneath it.

Each grid has **working days overdue** as rows and **Answered / Pending** counts
as columns, across all government departments. Answered delays end on the
substantive answer date; pending delays end on the saved assessment date. The
count excludes weekends and England and Wales bank holidays, but not recesses.
A “Less than 1” row covers deadlines that have passed with no subsequent working
day, such as a reply received over a weekend. Missing days between observed
delays display zero counts. Totals reconcile with late answers and overdue
pending questions in the department view.

On-time answers and questions still within their allowed response period are
excluded. Holding replies remain pending. These are tabling cohorts: older
outstanding questions outside the selected 30/90-day window are not included.
The JSON download includes `overdue_rows` and `overdue_day_basis: "working"`;
the existing Parquet resource retains the department counts. Rebuild the
performance package when upgrading an old snapshot without the delay rows.

Non-zero overdue counts link to the questions behind each cell. Column totals
link to all overdue questions of that type and status. Detail pages show the
question number and excerpt, a Parliament link, department, tabling date,
calculated response target, answer date where applicable, and working-day delay.
For example, `/performance/overdue/ordinary/pending/3/` lists ordinary questions
three working days overdue in the 30-day cohort; use `/all/` instead of `/3/` for
the column total. The 90-day pages use `/performance/overdue/period/90/`.

The snapshot stores each overdue question once in `overdue_questions`, with its
status and dates assessed at build time. Both periods select from those saved
records, so detail lists reconcile with the grid even if Parliament later updates
an answer. Only populated detail pages are generated; empty selections return
404. Snapshots without question details must be rebuilt before serving the site.

### Performance methodology

- Received means tabled within the selected period. Answered counts substantive
  answers to those questions recorded by the assessment date, rather than answers
  issued within the period. Holding answers remain waiting.
- Priority questions use their named date. Ordinary questions use the fifth working
  day on or after **the published date for answer**, counting that date as day one
  when it is a working day, excluding weekends and England and Wales bank holidays.
  Parliamentary recess days are not excluded. A deadline on the assessment date
  is still within the allowed period.
- This follows the [Table Office’s worked example, Q144](https://committees.parliament.uk/oralevidence/17713/pdf/#page=15)
  and [Government evidence, paragraph 27](https://committees.parliament.uk/writtenevidence/161782/html/).
  It replaces five working days after tabling. Counting from the published answer
  date gives a much closer match to the Committee’s 2023–24 departmental counts,
  despite the report describing the target as five days from tabling. Some
  discrepancies remain; this does not claim to reproduce official statistics exactly.
  Both dashboard views include the full methodology and source links.
- The checked-in `data/raw/bank_holidays.json` comes from
  [GOV.UK](https://www.gov.uk/bank-holidays.json), and is refreshed automatically on every `project fetch`, including the scheduled
  build. Its `refreshed_at` records the last successful refresh. Dataset builds use
  the cached file without network requests. Failed or invalid downloads leave the
  previous cache intact and fail the fetch command. Refresh validation requires all
  eight recurring holidays in every supplied year, including intervening years;
  moved dates, name qualifiers and additional holidays are accepted. This cannot
  detect an omitted one-off holiday that the source has never supplied.
  Builds fail on uncovered dates
  rather than silently counting holidays as working days.
- Questions are deduplicated by source ID: the last record in sorted month/file
  order wins. Departments use source IDs and the latest name in the 90-day
  window. Different IDs are not automatically merged after reorganisations.
- Withdrawn questions and non-government bodies (listed by ID in
  `performance.py`) are excluded. All departments is a sum of eligible questions.
  Waiting reflects the source status; session-ending closures not recorded as
  withdrawals may need separate treatment when a window crosses that boundary.
- Every required monthly file must exist. All departments present in the 90-day
  window appear for both periods/types, including zero-count rows.

The performance package contains `performance.parquet` with the counts, period
bounds and assessment date. `performance_snapshot.json` also records source
freshness and `ordinary_target_basis` and supplies the dashboard's JSON download.
Snapshots without the current target basis must be rebuilt. Both are generated files.
For a reproducible historical assessment of the available cache, Python callers
can pass `as_of_date` and `repo_root` to `create_performance_dataset`; this does
not reconstruct previous source snapshots. `aggregate_performance()` requires an
explicit `BankHolidays` calendar and performs no file or network access. The
`on_time_rate` dashboard metric is distinct from the downloaded `answered_on_time`
count; an undefined rate is represented as `None` in Python.

Run `script/test` for the Python, JavaScript DOM, lint and type checks. It installs
the pinned Node test dependencies with `npm ci`; Node 18 or later is required.
For direct pytest runs, run `npm ci --ignore-scripts` once first. The DOM test
executes DataTables 3.0.4 locally against both period pages, without
CDN requests, and covers heading accessibility, URLs, ties, undefined rates,
empty tables and the no-DataTables fallback. Keep the DataTables version in
`package.json` and the dashboard template in sync.

## Creating site extensions

The shared dataset site can register project-local Flask blueprints while sharing
its base template, navigation, assets and static build checks. Scaffold one file:

```bash
uv run dataset create-extension \
  --module uk_parl_written_questions.example \
  --title "Example page" \
  --route example
```

This creates `src/uk_parl_written_questions/example.py` and prints the factory
reference to **append** to `extensions` in `[tool.dataset.site]` in
`pyproject.toml`. It refuses to overwrite an existing file. `--repo-root` can
select another repository. The generated page works with `dataset site serve`,
`dataset site routes`, `dataset site check` and `dataset site build` after
registration.

Factories accept `SiteSettings` and return `SiteExtension` with a Flask blueprint,
explicit `BuildTarget` entries and optional `NavigationItem` entries. Templates
can extend `base.html`; use `site_path` or `url_for` to preserve deployment paths.
Each build target maps a URL to an output path relative to `_site`. Blueprint
static files are discovered automatically; give them a namespaced static URL
such as `/example/assets`. File collisions, reserved output directories and
paths escaping the build directory are rejected. Extension pages need real
static URLs for distinct states; query-string-only filters cannot be frozen.

The reusable extension support and scaffolder live in the `src/data_common`
submodule. Their changes need releasing in that repository and the parent
repository's submodule reference updating before a clean remote checkout can
use this dashboard.
