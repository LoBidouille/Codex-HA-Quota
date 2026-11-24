"""Convert the Codex App Server response into the dashboard's public data."""

import math


def _window(raw):
    minutes = raw.get("windowDurationMins")
    if type(minutes) is not int or minutes <= 0:
        return None
    used = raw.get("usedPercent")
    remaining = None
    if type(used) in (int, float) and math.isfinite(used) and 0 <= used <= 100:
        remaining = round(100 - used, 2)
    reset = raw.get("resetsAt")
    return {
        "minutes": minutes,
        "remaining": remaining,
        "reset_at": reset if type(reset) is int and reset > 0 else None,
    }


def buckets(result):
    grouped = result.get("rateLimitsByLimitId")
    available = dict(grouped) if isinstance(grouped, dict) else {}
    legacy = result.get("rateLimits")
    if isinstance(legacy, dict):
        available.setdefault(legacy.get("limitId") or "codex", legacy)
    return available


def snapshot(result, profiles, now, stale_after):
    available = buckets(result)
    pages = []
    for profile in profiles:
        bucket = available.get(profile["limit_id"])
        if not isinstance(bucket, dict):
            bucket = {}
        windows = []
        for name in ("primary", "secondary"):
            raw = bucket.get(name)
            window = _window(raw) if isinstance(raw, dict) else None
            if window is not None:
                windows.append(window)
        windows.sort(key=lambda window: window["minutes"])
        short = next((window for window in windows if window["minutes"] < 10080), None)
        week = next((window for window in windows if window["minutes"] == 10080), None)
        pages.append({"key": profile["key"], "title": profile["title"], "short": short, "week": week})
    return {"schema": 1, "observed_at": now, "stale_after": stale_after, "demo": False, "pages": pages}


def demo_snapshot(now, stale_after, start=None):
    start = now if start is None else start
    short_reset = start + 6120
    if now >= short_reset:
        short_reset += ((now - short_reset) // 18000 + 1) * 18000
    week_reset = start + 180000
    if now >= week_reset:
        week_reset += ((now - week_reset) // 604800 + 1) * 604800
    return {"schema": 1, "observed_at": now, "stale_after": stale_after, "demo": True, "pages": [
        {"key": "codex", "title": "Codex", "short": {
            "minutes": 300, "remaining": 72 if now < start + 6120 else 100, "reset_at": short_reset,
        }, "week": {
            "minutes": 10080, "remaining": 38 if now < start + 180000 else 100, "reset_at": week_reset,
        }},
    ]}
