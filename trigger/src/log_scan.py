"""Pure error scan over shipped device log files (SPEC-fleet-monitoring item 11).

Matches the device's logging format ("%H:%M:%S | LEVEL    | message"), not free
regex: a line is an error line when its second pipe-delimited field is an error
level. Raw traceback blocks are counted separately — ``logging.exception``
already emits a formatted ERROR line before the traceback text, so counting
both would double-count one incident; tracebacks only stand in for the error
count when no formatted error lines exist at all (defensive: content that
reached the file without the formatter).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

ERROR_LEVELS = frozenset({"ERROR", "CRITICAL"})
TRACEBACK_MARKER = "Traceback (most recent call last"
LOG_KEY_RE = re.compile(r"^v1/(?P<device>[^/]+)/logs/(?P<name>[^/]+\.log)$")
MAX_LINE_CHARS = 300


@dataclass(frozen=True)
class ErrorDigest:
    device_id: str
    log_name: str
    error_count: int
    traceback_count: int
    first_error: str
    last_error: str


def parse_log_key(key: str) -> Optional[Tuple[str, str]]:
    match = LOG_KEY_RE.match(key)
    if not match:
        return None
    return match.group("device"), match.group("name")


def _is_error_line(line: str) -> bool:
    parts = line.split("|", 2)
    return len(parts) == 3 and parts[1].strip() in ERROR_LEVELS


def scan(lines: Iterable[str], *, device_id: str, log_name: str) -> ErrorDigest:
    error_count = 0
    traceback_count = 0
    first_error = ""
    last_error = ""
    for raw in lines:
        line = raw.rstrip("\n")
        if _is_error_line(line):
            error_count += 1
            trimmed = line.strip()[:MAX_LINE_CHARS]
            if not first_error:
                first_error = trimmed
            last_error = trimmed
        elif line.lstrip().startswith(TRACEBACK_MARKER):
            traceback_count += 1
    if error_count == 0 and traceback_count:
        error_count = traceback_count
        first_error = first_error or f"{traceback_count} raw traceback(s), no formatted error line"
        last_error = last_error or first_error
    return ErrorDigest(
        device_id=device_id,
        log_name=log_name,
        error_count=error_count,
        traceback_count=traceback_count,
        first_error=first_error,
        last_error=last_error,
    )
