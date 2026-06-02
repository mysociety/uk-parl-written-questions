from __future__ import annotations

import calendar
import datetime
import json
from dataclasses import dataclass
from pathlib import Path

import httpx
import pandas as pd
import requests
import rich
from mysoc_validator import Popolo
from pydantic import BaseModel
from pydantic_store import PydanticDBM
from tqdm import tqdm

start_year = 2023
start_month = 9

# Raw data is stored monthly and committed to git for caching
data_dir = Path("data", "raw", "commons")
# Large parquet files are generated from raw data during build process
# These directories may not exist initially and are created as needed
package_dir = Path("data", "packages", "commons_written_questions")
interests_package = Path("data", "packages", "commons_written_questions_interests")


class StoredLongForm(BaseModel):
    question_text: str
    answer_text: str | None


StorageDBM = PydanticDBM[StoredLongForm]

longform_dir = Path("data", "raw", "longform")


def _month_str(date_tabled: str) -> str:
    return date_tabled[:7]


@dataclass(eq=True, order=True)
class Month:
    year: int
    month: int

    @classmethod
    def now(cls):
        now = datetime.datetime.now()
        return cls(now.year, now.month)

    @classmethod
    def range(cls, start: Month, end: Month):
        current = start
        while current <= end:
            yield current
            current += 1

    def start_date_iso(self):
        return f"{self.year}-{self.month:02d}-01"

    def end_date_iso(self):
        _, last_day = calendar.monthrange(self.year, self.month)
        return f"{self.year}-{self.month:02d}-{last_day}"

    def __str__(self):
        return f"{self.year}-{self.month:02d}"

    def __add__(self, months: int):
        new_month = self.month + months
        new_year = self.year
        while new_month > 12:
            new_month -= 12
            new_year += 1
        while new_month < 1:
            new_month += 12
            new_year -= 1
        return Month(new_year, new_month)

    def __sub__(self, months: int):
        return self.__add__(-months)


def get_data(start_date: str, end_date: str, skip: int, take_amount=100):
    url = (
        "https://questions-statements-api.parliament.uk/api/writtenquestions/questions"
    )
    params = {
        "tabledWhenFrom": start_date,
        "tabledWhenTo": end_date,
        "house": "Commons",
        "take": take_amount,
        "skip": skip,
    }
    response = requests.get(url, params=params)
    return response.json()["results"]


def get_data_for_month(month: Month, take_amount: int = 100, force: bool = True):
    file_name = f"{month}.json"

    file_path = data_dir / file_name
    if file_path.exists() and not force:
        return json.loads(file_path.read_text())

    rich.print(f"[blue]Fetching data for {month}[/blue]")

    data = []
    last_has_contents = True

    skip = 0
    while last_has_contents:
        new_data = get_data(month.start_date_iso(), month.end_date_iso(), skip)
        data += new_data
        last_has_contents = len(new_data) > 0
        skip += take_amount

    # Ensure raw data directory exists
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(data))
    return data


def get_all_data(force_recent: bool = False):
    start = Month(start_year, start_month)
    current = Month.now()
    three_months_ago = current - 3
    data = []

    for month in Month.range(start, current):
        recent = force_recent and month >= three_months_ago
        data.extend(get_data_for_month(month, force=recent))
    return data


def fetch_single_question(internal_id: int | str) -> StoredLongForm | None:
    url = f"https://questions-statements-api.parliament.uk/api/writtenquestions/questions/{internal_id}"
    try:
        response = httpx.get(url, timeout=30)
        if response.status_code != 200:
            rich.print(
                f"[yellow]Warning: {response.status_code} for question {internal_id}[/yellow]"
            )
            return None
        value = response.json()["value"]
        return StoredLongForm(
            question_text=value["questionText"],
            answer_text=value.get("answerText"),
        )
    except Exception as e:
        rich.print(f"[red]Error fetching question {internal_id}: {e}[/red]")
        return None


def enrich_truncated_questions(data: list[dict]) -> list[dict]:
    longform_dir.mkdir(parents=True, exist_ok=True)
    to_enrich = [
        item
        for item in data
        if len(item["value"].get("questionText") or "") == 255
        or len(item["value"].get("answerText") or "") == 255
    ]
    rich.print(
        f"[blue]Found {len(to_enrich)} entries with potentially truncated text[/blue]"
    )
    months_needed = {_month_str(item["value"]["dateTabled"]) for item in to_enrich}
    caches = {
        m: StorageDBM(longform_dir / f"{m}.sqlite", flag="c") for m in months_needed
    }
    for item in tqdm(to_enrich, desc="Enriching truncated questions", unit="q"):
        val = item["value"]
        internal_id = str(val["id"])
        cache = caches[_month_str(val["dateTabled"])]
        q_truncated = len(val.get("questionText") or "") == 255
        a_truncated = len(val.get("answerText") or "") == 255
        cached = cache.get(internal_id)
        needs_fetch = cached is None or (a_truncated and not cached.answer_text)
        if needs_fetch:
            fetched = fetch_single_question(internal_id)
            if fetched:
                cache[internal_id] = fetched
                cached = fetched
        if cached:
            if q_truncated:
                val["questionText"] = cached.question_text
            if a_truncated and cached.answer_text:
                val["answerText"] = cached.answer_text
    return data


def create_dataset():
    data = get_all_data()
    data = enrich_truncated_questions(data)
    df = pd.DataFrame([x["value"] for x in data])

    popolo = Popolo.from_parlparse()

    people = df["askingMemberId"].apply(  # type: ignore
        lambda x: popolo.persons.from_identifier(  # type: ignore
            str(x),
            scheme=Popolo.IdentifierScheme.MNIS,  # type: ignore
        )  # type: ignore
    )

    df["twfy_id"] = people.apply(lambda x: x.reduced_id())
    df["person_name"] = people.apply(lambda x: x.names[-1].nice_name())

    # drop askingMember column
    df = df.drop(columns=["askingMember", "answeringMember", "correctingMember"])

    def make_url(date: str, uin: str):
        str_date = date.split("T")[0]
        return f"https://questions-statements.parliament.uk/written-questions/detail/{str_date}/{uin}/"

    df["url"] = df.apply(lambda x: make_url(x["dateTabled"], x["uin"]), axis=1)

    # Ensure output directories exist
    package_dir.mkdir(parents=True, exist_ok=True)
    interests_package.mkdir(parents=True, exist_ok=True)

    df.to_parquet(package_dir / "written_questions.parquet")

    just_interests = df[df["memberHasInterest"] == True]  # noqa
    just_interests.to_parquet(interests_package / "written_questions_interests.parquet")
