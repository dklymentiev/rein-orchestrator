"""
Rein time budgets - how long a block or a whole run may take, in wall time.

A `timeout` limits one script or one process. A time budget limits the thing
the flow author cares about: how long until this block has produced its
result, and how long until the run is over, however many times the engine
was started and stopped in between. The start times are kept in the state
database (see ReinState), so a budget survives restarts and can be checked
by any process, including one that only came to check (`rein --sweep`).
"""

import re
from typing import Any, Optional

# Row name of the run itself in the time_budget table. Block names are never
# empty, so this cannot clash with one.
RUN_KEY = ""

MIN_SECONDS = 1
MAX_SECONDS = 30 * 24 * 3600

# A flow that declares this schema version or newer and sets no time_budget
# gets the default below. Older flows keep running without one, so upgrading
# the engine does not start stopping flows that were written before budgets.
DEFAULT_SINCE = (3, 4, 0)
DEFAULT_RUN_SECONDS = 24 * 3600

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_PATTERN = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")


def parse_time_budget(value: Any, where: str = "time_budget") -> Optional[int]:
    """Turn a time_budget value into seconds. None means no budget.

    Accepts a whole number of seconds (60) or a number with a unit
    ("90s", "30m", "2h", "1d"). Anything else is an error that names the
    field, so a typo stops the flow at load time and not hours later.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{where}: expected a duration such as 30m, got {value!r}")
    if isinstance(value, int):
        seconds = value
    elif isinstance(value, str):
        match = _PATTERN.match(value)
        if match:
            seconds = int(match.group(1)) * _UNITS[match.group(2)]
        elif value.strip().isdigit():
            seconds = int(value.strip())
        else:
            raise ValueError(f"{where}: expected a duration such as 90s, 30m, 2h or 1d, got {value!r}")
    else:
        raise ValueError(f"{where}: expected a duration such as 30m, got {value!r}")

    if seconds < MIN_SECONDS or seconds > MAX_SECONDS:
        raise ValueError(f"{where}: {value!r} is outside the allowed range (1 second to 30 days)")
    return seconds


def _version_tuple(text: Any) -> tuple:
    parts = []
    for piece in str(text).split(".")[:3]:
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def run_budget(config: dict) -> Optional[int]:
    """Time budget of the whole run, in seconds, or None."""
    explicit = parse_time_budget(config.get("time_budget"), "time_budget")
    if explicit is not None:
        return explicit
    if "schema_version" in config and _version_tuple(config["schema_version"]) >= DEFAULT_SINCE:
        return DEFAULT_RUN_SECONDS
    return None


def block_budgets(blocks: list) -> dict:
    """Map block name -> time budget in seconds, for blocks that set one."""
    budgets = {}
    for block in blocks or []:
        name = block.get("name") or block.get("stage", "unknown")
        seconds = parse_time_budget(block.get("time_budget"), f"blocks.{name}.time_budget")
        if seconds is not None:
            budgets[name] = seconds
    return budgets


def format_seconds(seconds: float) -> str:
    """Short human form for log lines: 95 -> '1m35s'."""
    seconds = int(seconds)
    parts = []
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return "".join(parts)
