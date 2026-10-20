"""Golden-output regression tests for :func:`helpers.get_dataframes`.

For every sample ``.fit`` file, decode it exactly as the production pipeline
does and compare all 7 returned DataFrames against the stored baseline snapshot
with :func:`pandas.testing.assert_frame_equal`. This is the primary guard that
optimizations do not change decoded output.

Run ``./.venv/bin/python tests/generate_baseline.py`` first if the baseline is
missing.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from conftest import (
    BASELINE_DIR,
    TABLE_NAMES,
    baseline_key,
    connect_activity_id,
    discover_sample_fit_files,
    is_watch_file,
)

import helpers

_MANIFEST_PATH = BASELINE_DIR / "manifest.json"


def _load_manifest() -> dict[str, object]:
    """Load the baseline manifest, failing clearly if it is missing.

    Returns:
        dict[str, object]: The parsed manifest.
    """
    if not _MANIFEST_PATH.exists():
        pytest.fail(
            "Baseline manifest missing. Generate it with:\n"
            "  ./.venv/bin/python tests/generate_baseline.py"
        )
    return json.loads(_MANIFEST_PATH.read_text())


_MANIFEST = _load_manifest()
_FILES_MANIFEST: dict[str, dict] = _MANIFEST.get("files", {})  # type: ignore[assignment]
_SKIPPED_MANIFEST: dict[str, str] = _MANIFEST.get("skipped", {})  # type: ignore[assignment]

# One test case per (file, table) so failures pinpoint the exact DataFrame.
_CASES = [
    (fit_path, table)
    for fit_path in discover_sample_fit_files()
    if baseline_key(fit_path) in _FILES_MANIFEST
    for table in TABLE_NAMES
]


def _decode_sample(fit_path: str) -> tuple[pd.DataFrame, ...]:
    """Decode a sample file mirroring the watch vs. Garmin Connect pipelines.

    Args:
        fit_path: Absolute path to a sample ``.fit`` file.

    Returns:
        tuple[pd.DataFrame, ...]: The 7 DataFrames in fixed order.
    """
    if is_watch_file(fit_path):
        return helpers.get_dataframes(fit_path)
    return helpers.get_dataframes(fit_path, connect_activity_id(fit_path))


def _load_baseline(key: str, table: str) -> pd.DataFrame:
    """Load a single baseline DataFrame snapshot in whichever format it was saved.

    Args:
        key: Sanitized per-file identifier.
        table: One of the 7 table names.

    Returns:
        pd.DataFrame: The baseline snapshot.
    """
    fmt = _FILES_MANIFEST[key]["formats"][table]
    if fmt == "parquet":
        return pd.read_parquet(BASELINE_DIR / f"{key}__{table}.parquet", engine="pyarrow")
    return pd.read_pickle(BASELINE_DIR / f"{key}__{table}.pkl")


@pytest.fixture(scope="session")
def decoded_cache() -> dict[str, tuple[pd.DataFrame, ...]]:
    """Session cache so each sample file is decoded once, not once per table.

    Returns:
        dict[str, tuple[pd.DataFrame, ...]]: Map of file path to decoded tuple.
    """
    return {}


@pytest.mark.parametrize(
    ("fit_path", "table"),
    _CASES,
    ids=[f"{baseline_key(p)}::{t}" for p, t in _CASES],
)
def test_decoder_matches_baseline(
    fit_path: str,
    table: str,
    decoded_cache: dict[str, tuple[pd.DataFrame, ...]],
) -> None:
    """Assert a freshly decoded DataFrame equals its golden baseline.

    Args:
        fit_path: Absolute path to the sample ``.fit`` file under test.
        table: The table (DataFrame) name being compared.
        decoded_cache: Session-scoped cache of decoded results.
    """
    if fit_path not in decoded_cache:
        decoded_cache[fit_path] = _decode_sample(fit_path)

    table_index = TABLE_NAMES.index(table)
    actual = decoded_cache[fit_path][table_index]
    expected = _load_baseline(baseline_key(fit_path), table)

    pd.testing.assert_frame_equal(actual, expected)


def test_all_sample_files_have_baseline() -> None:
    """Every sample file should be represented in the baseline manifest.

    Guards against silently dropping coverage if new fixtures are added.
    """
    sample_keys = {baseline_key(p) for p in discover_sample_fit_files()}
    baselined = set(_FILES_MANIFEST) | set(_SKIPPED_MANIFEST)
    missing = sample_keys - baselined
    assert not missing, f"Sample files missing from baseline: {sorted(missing)}"
