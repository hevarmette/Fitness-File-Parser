from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from helpers import (
    extract_date_from_filename_connect,
    extract_date_from_filename_watch,
    is_connect_filename,
    is_watch_filename,
)

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "example activities"


def test_sample_files_classification() -> None:
    """Verify that all sample .fit files in example activities are correctly classified."""
    fit_files = sorted(SAMPLE_DIR.glob("**/*.fit"))
    assert len(fit_files) == 22

    for path in fit_files:
        name = path.name
        is_watch = is_watch_filename(name)
        is_connect = is_connect_filename(name)

        # Every sample file must be either watch or connect, never both, never neither
        assert is_watch != is_connect, f"Ambiguous classification for {name}"

        if is_watch:
            # Must extract date cleanly without error
            dt = extract_date_from_filename_watch(name)
            assert isinstance(dt, datetime)
            assert dt.tzinfo == timezone.utc
        else:
            dt = extract_date_from_filename_connect(name)
            assert isinstance(dt, datetime)


def test_is_watch_filename_patterns() -> None:
    """Verify positive and negative cases for is_watch_filename."""
    assert is_watch_filename("2025-07-27-07-19-09.fit")
    assert is_watch_filename("/path/to/2025-07-27-07-19-09.fit")

    # Connect format should be False
    assert not is_watch_filename("2022-06-09T11.26.06+00.00_8983936914.fit")
    # Wrong extension
    assert not is_watch_filename("2025-07-27-07-19-09.json")
    # Invalid date pattern
    assert not is_watch_filename("2025-07-27-07-19.fit")
    assert not is_watch_filename("random_name.fit")


def test_is_connect_filename_patterns() -> None:
    """Verify positive and negative cases for is_connect_filename."""
    assert is_connect_filename("2022-06-09T11.26.06+00.00_8983936914.fit")
    assert is_connect_filename("/path/to/2022-06-09T11.26.06+00.00_8983936914.fit")

    # Watch format should be False
    assert not is_connect_filename("2025-07-27-07-19-09.fit")
    # Wrong extension
    assert not is_connect_filename("2022-06-09T11.26.06+00.00_8983936914_summary.json")
    # Missing activity id
    assert not is_connect_filename("2022-06-09T11.26.06+00.00.fit")
