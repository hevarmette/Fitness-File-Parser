"""Generate the golden-output baseline for the FIT decoder.

Runs the *current, unmodified* :func:`helpers.get_dataframes` over every sample
``.fit`` file and serializes all 7 returned DataFrames (order:
``lap, record, file_id, activity, session, length, event``) into
``tests/baseline/``. The regression suite later reloads these snapshots and
compares them with :func:`pandas.testing.assert_frame_equal`.

Serialization format
--------------------
Snapshots are written as **parquet** (via ``pyarrow``) when a DataFrame can be
round-tripped losslessly. Some FIT-derived columns are genuinely
mixed-type ``object`` columns (e.g. the ``event.event`` column mixes ``str``
and ``int``), which Arrow/parquet cannot represent without lossy coercion.
Those DataFrames fall back to **pickle**, which preserves the exact dtypes and
content required for ``assert_frame_equal``. Each snapshot's format is recorded
in a per-file JSON manifest so the loader knows how to read it back.

The production pipelines are mirrored exactly:

* Watch files (``YYYY-MM-DD-HH-MM-SS.fit``) → ``get_dataframes(fname)``.
* Garmin Connect files (``{isotimestamp}_{activity_id}.fit``) →
  ``get_dataframes(fname, activity_id)``.

Any file whose decode raises (the parser only raises on a fatal
``activity_df`` failure, exactly as production treats it) is skipped and
recorded in the manifest with the reason, rather than aborting the baseline.

Run with the project virtualenv::

    ./.venv/bin/python tests/generate_baseline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# Make the repo root importable so ``import helpers`` works when this script is
# run directly (``python tests/generate_baseline.py``).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from conftest import (  # noqa: E402  (local test helper module)
    BASELINE_DIR,
    TABLE_NAMES,
    baseline_key,
    connect_activity_id,
    discover_sample_fit_files,
    is_watch_file,
)

import helpers  # noqa: E402  (import after sys.path tweak)


def _decode_sample(fit_path: str) -> tuple[pd.DataFrame, ...]:
    """Decode a single sample file the same way the production pipeline does.

    Args:
        fit_path: Absolute path to a sample ``.fit`` file.

    Returns:
        tuple[pd.DataFrame, ...]: The 7 DataFrames in fixed order
        ``(lap, record, file_id, activity, session, length, event)``.

    Raises:
        ValueError: Propagated from :func:`helpers.get_dataframes` when the
            fatal ``activity_df`` construction fails.
    """
    if is_watch_file(fit_path):
        return helpers.get_dataframes(fit_path)
    activity_id = connect_activity_id(fit_path)
    return helpers.get_dataframes(fit_path, activity_id)


def _roundtrips_via_parquet(df: pd.DataFrame, path: Path) -> bool:
    """Try to write ``df`` to parquet and confirm it reloads identically.

    Args:
        df: The DataFrame to snapshot.
        path: Destination parquet path.

    Returns:
        bool: ``True`` if the parquet write + reload equals ``df`` exactly;
        ``False`` (and no file left behind) otherwise.
    """
    try:
        df.to_parquet(path, engine="pyarrow", index=True)
        reloaded = pd.read_parquet(path, engine="pyarrow")
        pd.testing.assert_frame_equal(df, reloaded)
        return True
    except Exception:
        # Mixed-type object columns (valid FIT data) can't round-trip via Arrow.
        if path.exists():
            path.unlink()
        return False


def _snapshot_dataframe(df: pd.DataFrame, key: str, table: str) -> str:
    """Serialize one DataFrame, preferring parquet and falling back to pickle.

    Args:
        df: The DataFrame to serialize.
        key: Sanitized per-file identifier.
        table: One of the 7 table names.

    Returns:
        str: The format used, ``"parquet"`` or ``"pickle"``.
    """
    parquet_path = BASELINE_DIR / f"{key}__{table}.parquet"
    if _roundtrips_via_parquet(df, parquet_path):
        return "parquet"

    pickle_path = BASELINE_DIR / f"{key}__{table}.pkl"
    df.to_pickle(pickle_path)
    return "pickle"


def generate_baseline() -> dict[str, object]:
    """Decode every sample file and write baseline snapshots + a manifest.

    Returns:
        dict[str, object]: The manifest describing decoded files, per-table
        snapshot formats, and any skipped files with their failure reason.
    """
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {"files": {}, "skipped": {}, "table_names": list(TABLE_NAMES)}
    files_manifest: dict[str, object] = manifest["files"]  # type: ignore[assignment]
    skipped_manifest: dict[str, str] = manifest["skipped"]  # type: ignore[assignment]

    for fit_path in discover_sample_fit_files():
        key = baseline_key(fit_path)
        try:
            dataframes = _decode_sample(fit_path)
        except Exception as exc:  # matches production: only fatal activity_df failures
            skipped_manifest[key] = f"{type(exc).__name__}: {exc}"
            print(f"[SKIP] {key}: {skipped_manifest[key]}")
            continue

        formats: dict[str, str] = {}
        for table, df in zip(TABLE_NAMES, dataframes):
            formats[table] = _snapshot_dataframe(df, key, table)

        files_manifest[key] = {
            "source": str(Path(fit_path).relative_to(_REPO_ROOT)),
            "is_watch": is_watch_file(fit_path),
            "formats": formats,
        }
        print(f"[OK]   {key}: {formats}")

    manifest_path = BASELINE_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(
        f"\nBaseline written to {BASELINE_DIR} "
        f"({len(files_manifest)} files, {len(skipped_manifest)} skipped)."
    )
    return manifest


if __name__ == "__main__":
    generate_baseline()
