"""Shared pytest fixtures and helpers for the FIT-parser regression suite.

The fixtures here expose the real sample ``.fit`` files under
``example activities/`` (note the space in the directory name) so decoder and
SQL-writer tests can run without a live database.

The suite mirrors *production* behavior: watch-exported files
(``YYYY-MM-DD-HH-MM-SS.fit``) are decoded with ``get_dataframes(fname)`` while
Garmin Connect files (``{isotimestamp}_{activity_id}.fit``) are decoded with
``get_dataframes(fname, activity_id)`` — the same way the two ``parse_fit_*``
entry points call it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# Repo root is the parent of the ``tests/`` directory that holds this file.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Directory of golden-baseline parquet snapshots produced by generate_baseline.py.
BASELINE_DIR = Path(__file__).resolve().parent / "baseline"

# Fixed order of the 7 DataFrames returned by helpers.get_dataframes.
TABLE_NAMES: tuple[str, ...] = (
    "lap",
    "record",
    "file_id",
    "activity",
    "session",
    "length",
    "event",
)

# Watch files are named YYYY-MM-DD-HH-MM-SS.fit (no activity_id embedded).
# Everything else in the sample set is a Garmin Connect export whose activity_id
# is the numeric suffix after the underscore.
_WATCH_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$")


def is_watch_file(fit_path: str | os.PathLike[str]) -> bool:
    """Return ``True`` if ``fit_path`` follows the watch-export naming scheme.

    Args:
        fit_path: Path to a ``.fit`` file.

    Returns:
        bool: ``True`` for ``YYYY-MM-DD-HH-MM-SS.fit`` watch files, ``False`` for
        Garmin Connect ``{isotimestamp}_{activity_id}.fit`` files.
    """
    stem = Path(fit_path).stem
    return bool(_WATCH_STEM_RE.match(stem))


def connect_activity_id(fit_path: str | os.PathLike[str]) -> str:
    """Extract the Garmin Connect ``activity_id`` from a filename.

    Mirrors ``helpers.get_user_activity_details`` (split on ``_``, take the
    segment after the timestamp, drop the extension).

    Args:
        fit_path: Path to a Garmin Connect ``.fit`` file.

    Returns:
        str: The numeric activity id, e.g. ``"8983936914"``.
    """
    name = os.path.basename(str(fit_path))
    activity_id = name.split("_")[1]
    if "." in activity_id:
        activity_id = activity_id.split(".")[0]
    return activity_id


def baseline_key(fit_path: str | os.PathLike[str]) -> str:
    """Build a filesystem-safe identifier for a sample file's baseline snapshots.

    Includes the parent-folder name so that files with identical basenames in
    different sub-folders do not collide.

    Args:
        fit_path: Path to a sample ``.fit`` file.

    Returns:
        str: A sanitized key such as ``cycling__2022-06-09T11-26-06_00-00_8983936914``.
    """
    path = Path(fit_path)
    raw = f"{path.parent.name}__{path.stem}"
    # Replace any character that is awkward in a filename with an underscore.
    return re.sub(r"[^0-9A-Za-z._-]", "_", raw)


def discover_sample_fit_files() -> list[str]:
    """Return all sample ``.fit`` files as sorted absolute path strings.

    Returns:
        list[str]: Absolute paths under ``example activities/**/*.fit``.
    """
    sample_root = REPO_ROOT / "example activities"
    return sorted(str(p.resolve()) for p in sample_root.glob("**/*.fit"))


@pytest.fixture(scope="session")
def sample_fit_files() -> list[str]:
    """Session-scoped fixture yielding every sample ``.fit`` file (absolute paths).

    Returns:
        list[str]: Absolute paths to the sample FIT files bundled under
        ``example activities/``.
    """
    files = discover_sample_fit_files()
    assert files, "No sample .fit files found under 'example activities/'"
    return files


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip ``@pytest.mark.db`` tests when no database is configured.

    Decoder and SQL-writer tests never require a database; the ``db`` marker is
    reserved for future round-trip tests (Wave 2). When the ``DB_UI_LOCAL``
    environment variable is unset, any ``db``-marked test is skipped rather than
    failing to connect.

    Args:
        config: The active pytest configuration (unused, required by the hook).
        items: Collected test items to (possibly) mark for skipping.
    """
    if os.getenv("DB_UI_LOCAL"):
        return
    skip_db = pytest.mark.skip(reason="requires a live database; DB_UI_LOCAL is unset")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)
