from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class WeeklyWindow:
    weekday: int  # 0=Monday ... 6=Sunday
    start_time: time
    end_time: time


@dataclass(frozen=True)
class ExceptionWindow:
    kind: str  # "time_off" or "available"
    starts_at: datetime
    ends_at: datetime


def _safe_zoneinfo(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _require_aware(dt: datetime, name: str) -> None:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{name} must be timezone-aware")


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    intervals_sorted = sorted(intervals, key=lambda x: (x[0], x[1]))
    out: list[tuple[datetime, datetime]] = []
    cur_start, cur_end = intervals_sorted[0]

    for start, end in intervals_sorted[1:]:
        if start <= cur_end:
            if end > cur_end:
                cur_end = end
            continue
        out.append((cur_start, cur_end))
        cur_start, cur_end = start, end

    out.append((cur_start, cur_end))
    return out


def _subtract_intervals(
    available: list[tuple[datetime, datetime]],
    blocks: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not available:
        return []
    if not blocks:
        return available

    blocks_merged = _merge_intervals(blocks)
    out: list[tuple[datetime, datetime]] = []

    for a_start, a_end in available:
        segments = [(a_start, a_end)]

        for b_start, b_end in blocks_merged:
            next_segments: list[tuple[datetime, datetime]] = []
            for s_start, s_end in segments:
                if b_end <= s_start or b_start >= s_end:
                    next_segments.append((s_start, s_end))
                    continue

                if b_start > s_start:
                    next_segments.append((s_start, b_start))
                if b_end < s_end:
                    next_segments.append((b_end, s_end))

            segments = next_segments
            if not segments:
                break

        out.extend(segments)

    return _merge_intervals([seg for seg in out if seg[0] < seg[1]])


def compute_available_intervals(
    *,
    tz_name: str,
    weekly_windows: list[WeeklyWindow],
    exceptions: list[ExceptionWindow],
    start_at: datetime,
    end_at: datetime,
) -> list[tuple[datetime, datetime]]:
    """Compute availability intervals within [start_at, end_at) in UTC.

    Weekly windows are interpreted in `tz_name`.
    Exceptions are assumed to already be timezone-aware.
    """

    _require_aware(start_at, "start_at")
    _require_aware(end_at, "end_at")
    if end_at <= start_at:
        return []

    tz = _safe_zoneinfo(tz_name)

    start_utc = start_at.astimezone(timezone.utc)
    end_utc = end_at.astimezone(timezone.utc)

    start_local = start_utc.astimezone(tz)
    end_local = end_utc.astimezone(tz)

    start_date = start_local.date()
    end_date = end_local.date()

    base: list[tuple[datetime, datetime]] = []

    weekly_by_day: dict[int, list[WeeklyWindow]] = {}
    for window in weekly_windows:
        weekly_by_day.setdefault(int(window.weekday), []).append(window)

    day: date = start_date
    while day <= end_date:
        weekday = day.weekday()
        for window in weekly_by_day.get(weekday, []):
            if window.end_time <= window.start_time:
                continue

            local_start = datetime.combine(day, window.start_time, tzinfo=tz)
            local_end = datetime.combine(day, window.end_time, tzinfo=tz)

            start = local_start.astimezone(timezone.utc)
            end = local_end.astimezone(timezone.utc)

            if end <= start_utc or start >= end_utc:
                continue

            base.append((max(start, start_utc), min(end, end_utc)))

        day += timedelta(days=1)

    blocks: list[tuple[datetime, datetime]] = []

    for exc in exceptions:
        _require_aware(exc.starts_at, "exception.starts_at")
        _require_aware(exc.ends_at, "exception.ends_at")
        if exc.ends_at <= exc.starts_at:
            continue

        start = exc.starts_at.astimezone(timezone.utc)
        end = exc.ends_at.astimezone(timezone.utc)
        if end <= start_utc or start >= end_utc:
            continue

        clipped = (max(start, start_utc), min(end, end_utc))

        if exc.kind == "available":
            base.append(clipped)
        elif exc.kind == "time_off":
            blocks.append(clipped)

    base_merged = _merge_intervals([i for i in base if i[0] < i[1]])
    return _subtract_intervals(base_merged, blocks)


def summarize_availability(
    *,
    tz_name: str,
    weekly_windows: list[WeeklyWindow],
    exceptions: list[ExceptionWindow],
    start_at: datetime,
    end_at: datetime,
) -> dict:
    intervals = compute_available_intervals(
        tz_name=tz_name,
        weekly_windows=weekly_windows,
        exceptions=exceptions,
        start_at=start_at,
        end_at=end_at,
    )

    minutes_available = int(sum((end - start).total_seconds() // 60 for start, end in intervals))

    next_available_at = intervals[0][0].isoformat().replace("+00:00", "Z") if intervals else None

    return {
        "has_availability": bool(intervals),
        "next_available_at": next_available_at,
        "minutes_available": minutes_available,
    }
