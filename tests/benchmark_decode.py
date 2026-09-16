"""Decode benchmark harness for :func:`helpers.get_dataframes`.

Times decoding over the sample ``.fit`` set with :func:`time.perf_counter`
(``N`` runs, reporting the mean per file and the total) and reports, per file,
how many FIT data-message frames are *iterated* versus how many are actually
*used* by the decoder.

"Frames used" counts frames whose ``name`` maps to one of the 7 tables the
schema uses (``record``, ``lap``, ``file_id``, ``activity``, ``session``,
``length``, ``event``). The gap between iterated and used frames motivates the
Wave 2 "skip unused message types early" optimization.

This is intentionally read-only: it does not import or modify parser code paths
beyond calling the public :func:`helpers.get_dataframes`. It never touches the
database or the network (reverse geocoding lives in ``parse_fit_watch.py``, not
in ``get_dataframes``).

Run with the project virtualenv::

    ./.venv/bin/python tests/benchmark_decode.py
    ./.venv/bin/python tests/benchmark_decode.py --runs 10
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import fitdecode

# Make the repo root importable when run directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from conftest import (  # noqa: E402
    connect_activity_id,
    discover_sample_fit_files,
    is_watch_file,
)

import helpers  # noqa: E402

# Message names the schema actually consumes (see helpers.get_dataframes).
USED_MESSAGE_NAMES: frozenset[str] = frozenset(
    {"record", "lap", "file_id", "activity", "session", "length", "event"}
)


@dataclass(frozen=True)
class FileBenchmark:
    """Benchmark result for one sample file.

    Attributes:
        name: Basename of the sample file.
        mean_seconds: Mean wall-clock decode time across runs.
        frames_iterated: Total FIT data-message frames iterated.
        frames_used: Frames whose message name is consumed by the decoder.
    """

    name: str
    mean_seconds: float
    frames_iterated: int
    frames_used: int


def _decode(fit_path: str) -> None:
    """Decode one file exactly as the production pipeline would.

    Args:
        fit_path: Absolute path to a sample ``.fit`` file.
    """
    if is_watch_file(fit_path):
        helpers.get_dataframes(fit_path)
    else:
        helpers.get_dataframes(fit_path, connect_activity_id(fit_path))


def _count_frames(fit_path: str) -> tuple[int, int]:
    """Count total vs. used FIT data-message frames for one file.

    Args:
        fit_path: Absolute path to a sample ``.fit`` file.

    Returns:
        tuple[int, int]: ``(frames_iterated, frames_used)``.
    """
    iterated = 0
    used = 0
    with fitdecode.FitReader(fit_path) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.records.FitDataMessage):
                continue
            iterated += 1
            if frame.name in USED_MESSAGE_NAMES:
                used += 1
    return iterated, used


def benchmark(runs: int = 5) -> list[FileBenchmark]:
    """Benchmark decode time and frame usage across all sample files.

    Args:
        runs: Number of timed decode repetitions per file (mean is reported).

    Returns:
        list[FileBenchmark]: One result per sample file.
    """
    results: list[FileBenchmark] = []
    for fit_path in discover_sample_fit_files():
        # One untimed warm-up decode to prime OS file cache, then N timed runs.
        _decode(fit_path)
        elapsed = 0.0
        for _ in range(runs):
            start = time.perf_counter()
            _decode(fit_path)
            elapsed += time.perf_counter() - start
        iterated, used = _count_frames(fit_path)
        results.append(
            FileBenchmark(
                name=Path(fit_path).name,
                mean_seconds=elapsed / runs,
                frames_iterated=iterated,
                frames_used=used,
            )
        )
    return results


def print_report(results: list[FileBenchmark], runs: int) -> None:
    """Print a human-readable benchmark table and totals.

    Args:
        results: Benchmark results to display.
        runs: Number of runs used (for the header).
    """
    print(f"Decode benchmark (mean of {runs} runs per file)\n")
    header = f"{'file':52} {'mean ms':>10} {'iterated':>10} {'used':>7} {'used %':>8}"
    print(header)
    print("-" * len(header))

    total_time = 0.0
    total_iter = 0
    total_used = 0
    for r in results:
        total_time += r.mean_seconds
        total_iter += r.frames_iterated
        total_used += r.frames_used
        used_pct = (100.0 * r.frames_used / r.frames_iterated) if r.frames_iterated else 0.0
        print(
            f"{r.name:52} {r.mean_seconds * 1000:10.2f} "
            f"{r.frames_iterated:10d} {r.frames_used:7d} {used_pct:7.1f}%"
        )

    print("-" * len(header))
    n = len(results)
    mean_per_file = (total_time / n) if n else 0.0
    overall_pct = (100.0 * total_used / total_iter) if total_iter else 0.0
    print(
        f"{'TOTAL / MEAN':52} {mean_per_file * 1000:10.2f} "
        f"{total_iter:10d} {total_used:7d} {overall_pct:7.1f}%"
    )
    print(
        f"\n{n} files | total decode time {total_time * 1000:.1f} ms "
        f"| mean per file {mean_per_file * 1000:.2f} ms "
        f"| {total_used}/{total_iter} frames used ({overall_pct:.1f}%)"
    )


def main() -> None:
    """CLI entry point: parse args, run the benchmark, print the report."""
    parser = argparse.ArgumentParser(description="Benchmark get_dataframes decode time.")
    parser.add_argument(
        "--runs", type=int, default=5, help="Timed repetitions per file (default: 5)."
    )
    args = parser.parse_args()
    print_report(benchmark(runs=args.runs), runs=args.runs)


if __name__ == "__main__":
    main()
