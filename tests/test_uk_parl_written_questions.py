from __future__ import annotations

from pathlib import Path

import pytest

from uk_parl_written_questions import fetch


def test_true_is_true():
    assert True is True


@pytest.fixture
def longform_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Point the long-form cache at a writable directory for the test.
    """
    monkeypatch.setattr(fetch, "longform_dir", tmp_path)
    return tmp_path


def test_new_cache_is_readable_by_other_users(longform_dir: Path) -> None:
    """
    Create the cache readable by the user that commits the build output.

    The build runs as root inside the container, but the workflow step that
    commits the result runs as the host user, and cannot add a file it is
    not allowed to read.
    """
    fetch.open_longform_cache("2030-01")

    mode = (longform_dir / "2030-01.sqlite").stat().st_mode
    assert mode & 0o044 == 0o044


def test_existing_private_cache_is_repaired(longform_dir: Path) -> None:
    """
    Widen the permissions of a cache written before the mode was set.
    """
    path = longform_dir / "2030-02.sqlite"
    fetch.StorageDBM(path, flag="c", mode=0o600)
    assert path.stat().st_mode & 0o044 == 0

    fetch.open_longform_cache("2030-02")

    assert path.stat().st_mode & 0o044 == 0o044


def test_cache_stores_and_returns_entries(longform_dir: Path) -> None:
    """
    Keep the cache usable for reading and writing entries.
    """
    cache = fetch.open_longform_cache("2030-03")

    cache["1"] = fetch.StoredLongForm(question_text="question", answer_text="answer")

    stored = cache.get("1")
    assert stored is not None
    assert stored.question_text == "question"
    assert stored.answer_text == "answer"
