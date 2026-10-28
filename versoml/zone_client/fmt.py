"""How the client zone writes money and dates: "RON 3,200.00" and "29 Oct 2026, 23:59" (Bucharest time, 24-hour).

Month names come from a fixed list, so the output never depends on the server's locale.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Bucharest")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def money(value: Any, currency: str | None = "RON") -> str:
    """3200 -> "RON 3,200.00"."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{currency or 'RON'} {amount:,.2f}"


def to_local(value: Any) -> datetime | None:
    """A datetime or an ISO string, in Bucharest time. Naive values are read as UTC; anything else gives None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=TZ)
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def fmt_date(value: Any) -> str:
    """"29 Oct 2026" (a plain date stays as it is; a datetime is read in Bucharest time)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return f"{value.day} {MONTHS[value.month - 1]} {value.year}"
    dt = to_local(value)
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}" if dt else ""


def fmt_datetime(value: Any) -> str:
    """"29 Oct 2026, 23:59"."""
    dt = to_local(value)
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}, {dt:%H:%M}" if dt else ""


def fmt_deadline(value: Any) -> str:
    """"29 Oct, 23:59": the short form for prompts, where the year is obvious."""
    dt = to_local(value)
    return f"{dt.day} {MONTHS[dt.month - 1]}, {dt:%H:%M}" if dt else ""
