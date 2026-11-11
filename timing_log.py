"""Timing and slow-file diagnostics for the FIT parsing pipelines.

When one activity occasionally takes many minutes, the question is *where* the
time goes: reading FIT frames, building DataFrames, the Nominatim reverse-geocode
request, or a database insert. This module answers that with two tools:

* :class:`StageTimer` logs how long each named stage of a file took, with sizes
  (frame counts, row counts) so a slow stage can be compared against how much
  data it handled. Stages at or above ``SLOW_STAGE_SECONDS`` are logged as
  WARNING so they stand out.
* The hang watchdog (``watch_hangs=True``) uses :mod:`faulthandler` to write the
  current Python stack to the log every ``STACK_DUMP_INTERVAL_SECONDS`` while a
  file is still being processed. A stage that never finishes logs nothing by
  itself, but repeated stack dumps show exactly which line is stuck (e.g. inside
  ``requests`` waiting on a socket, ``fitdecode`` reading frames, or ``psycopg``
  waiting on the database).

Output goes to the console and is appended to ``timing.log`` in the repo root.
Call :func:`configure_logging` once from a pipeline's ``__main__``; when it has
not been called (tests, library use) the INFO lines are silent.
"""

from __future__ import annotations

import faulthandler
import logging
import sys
import time
from pathlib import Path
from typing import IO, Any

logger = logging.getLogger("fit_parser")

LOG_PATH = Path(__file__).resolve().parent / "timing.log"

# A stage taking at least this long is logged as a WARNING instead of INFO.
SLOW_STAGE_SECONDS = 30.0
# While a file is being processed, dump the Python stack this often (seconds).
STACK_DUMP_INTERVAL_SECONDS = 60

# Open handle on timing.log, shared with faulthandler (which needs a real file).
_dump_stream: IO[str] | None = None


def configure_logging(level: int = logging.INFO) -> None:
    """Send ``fit_parser`` logs to the console and append them to ``timing.log``.

    Safe to call more than once; handlers are only added the first time.

    Args:
        level: Minimum level to record (INFO shows every stage, WARNING only
            the slow ones).
    """
    global _dump_stream
    if logger.handlers:
        return

    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    console_handler = logging.StreamHandler()
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)

    # faulthandler writes tracebacks straight to this file descriptor.
    _dump_stream = file_handler.stream


class StageTimer:
    """Logs the duration of each stage of processing one file.

    Call :meth:`lap` at the end of every stage; it reports the time since the
    previous lap (or since creation). Call :meth:`finish` when the file is done.

    Args:
        label: Identifies the file in every log line (usually the file name).
        watch_hangs: Also start the stack-dump watchdog for this file. Only the
            outermost caller (the pipeline loop) should do this, because
            ``faulthandler`` has a single global timer.
    """

    def __init__(self, label: str, watch_hangs: bool = False) -> None:
        self.label = label
        self._watching = watch_hangs
        self._started = self._last = time.perf_counter()
        if watch_hangs:
            faulthandler.dump_traceback_later(
                STACK_DUMP_INTERVAL_SECONDS, repeat=True, file=_dump_stream or sys.stderr
            )
            logger.info("%s | START", label)

    def lap(self, stage: str, **details: Any) -> float:
        """Log how long the stage that just ended took.

        Args:
            stage: Short name of the stage that just finished.
            **details: Sizes worth comparing against the time, e.g. ``rows=1200``.

        Returns:
            float: Seconds since the previous lap.
        """
        now = time.perf_counter()
        elapsed = now - self._last
        self._last = now
        level = logging.WARNING if elapsed >= SLOW_STAGE_SECONDS else logging.INFO
        extra = " ".join(f"{key}={value}" for key, value in details.items())
        logger.log(level, "%s | %-30s %8.2fs  %s", self.label, stage, elapsed, extra)
        return elapsed

    def finish(self, outcome: str = "done") -> None:
        """Log the file's total time and stop the hang watchdog if it was started.

        Args:
            outcome: Short note on how the file ended (e.g. ``"skipped"``).
        """
        if self._watching:
            faulthandler.cancel_dump_traceback_later()
            self._watching = False
        total = time.perf_counter() - self._started
        level = logging.WARNING if total >= SLOW_STAGE_SECONDS else logging.INFO
        logger.log(level, "%s | %-30s %8.2fs  (%s)", self.label, "TOTAL", total, outcome)
