#!/usr/bin/env python3
"""Canonical game-time helpers.

Internal time is stored as _time_tick (minutes since Day 1 00:00).
Display time uses the Chinese format "第 N 日 HH:MM".

All tools should import from here instead of duplicating time logic.
"""

from __future__ import annotations

import re

# "第 1 日 20:00"
_DISPLAY_RE = re.compile(r"\u7b2c\s*(\d+)\s*\u65e5\s*(\d{1,2}):(\d{2})")


def display_to_tick(display: str) -> int:
    """Parse '\u7b2c 1 \u65e5 20:00' -> 1200 (minutes)."""
    m = _DISPLAY_RE.search(display or "")
    if not m:
        raise ValueError(f"Cannot parse display time: {display!r}")
    day = int(m.group(1))
    hour = int(m.group(2))
    minute = int(m.group(3))
    return (day - 1) * 1440 + hour * 60 + minute


def tick_to_display(tick: int) -> str:
    """Convert 1200 -> '\u7b2c 1 \u65e5 20:00'."""
    day = tick // 1440 + 1
    minute_of_day = tick % 1440
    hour = minute_of_day // 60
    minute = minute_of_day % 60
    return f"\u7b2c {day} \u65e5 {hour:02d}:{minute:02d}"


def tick_from_campaign(campaign_state: dict) -> int:
    """Get canonical _time_tick from campaign state, computing if missing."""
    if "_time_tick" in campaign_state:
        try:
            return int(campaign_state["_time_tick"])
        except (TypeError, ValueError):
            pass
    # backward compat: parse from current_time
    display = campaign_state.get("current_time", "")
    try:
        tick = display_to_tick(display) if display else 0
    except ValueError:
        tick = 0
    campaign_state["_time_tick"] = tick
    return tick


def sync_campaign_time(campaign_state: dict) -> None:
    """Ensure current_time and _time_tick are consistent."""
    tick = tick_from_campaign(campaign_state)
    campaign_state["_time_tick"] = tick
    campaign_state["current_time"] = tick_to_display(tick)


def parse_interval_minutes(value: str) -> int | None:
    """Parse a Chinese interval string into minutes. Returns None on failure."""
    text = value or ""
    hour_match = re.search(r"(\d+)\s*\u5c0f\u65f6", text)
    minute_match = re.search(r"(\d+)\s*\u5206\u949f", text)
    total = 0
    if hour_match:
        total += int(hour_match.group(1)) * 60
    if minute_match:
        total += int(minute_match.group(1))
    if total:
        return total
    numeric_match = re.search(r"(\d+)", text)
    if numeric_match:
        return int(numeric_match.group(1))
    return None


def parse_time_delta(delta: str) -> int:
    """Parse a Chinese time delta string into total minutes."""
    if not delta or delta in ("\u65e0", "none", "0"):
        return 0
    total = parse_interval_minutes(delta) or 0
    if total == 0:
        day_match = re.search(r"(\d+)\s*\u5929", delta)
        if day_match:
            total += int(day_match.group(1)) * 1440
    return total


def advance_tick(from_tick: int, minutes: int) -> int:
    """Advance a tick by N minutes."""
    return from_tick + minutes
