"""Local-time to ISO 8601 helper for Los Angeles (handles PST/PDT without needing tzdata)."""

from datetime import datetime, timedelta


def _nth_sunday(year, month, n):
    d = datetime(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)  # first Sunday
    return d + timedelta(weeks=n - 1)


def la_iso(naive):
    """naive: datetime in LA wall-clock time -> '2026-11-03T19:30:00-08:00'."""
    start = _nth_sunday(naive.year, 3, 2).replace(hour=2)   # DST starts 2nd Sunday of March, 2:00
    end = _nth_sunday(naive.year, 11, 1).replace(hour=2)    # ends 1st Sunday of November, 2:00
    offset = "-07:00" if start <= naive < end else "-08:00"
    return naive.strftime("%Y-%m-%dT%H:%M:%S") + offset
