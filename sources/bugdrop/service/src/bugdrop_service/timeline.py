"""Derived UI-state timeline: visibility intervals and route changes from ui_state snapshots."""

from __future__ import annotations

from typing import Any


def ui_state_timeline(snapshots: list[dict[str, Any]], report_ts: float) -> dict[str, Any]:
    snaps = sorted((s for s in snapshots if "ts" in s), key=lambda s: float(s["ts"]))
    intervals: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    for s in snaps:
        vis = s.get("visibility")
        if vis and (not intervals or intervals[-1]["state"] != vis):
            if intervals:
                intervals[-1]["end"] = s["ts"]
            intervals.append({"state": vis, "start": s["ts"], "end": None})
        route = s.get("route")
        if route and (not routes or routes[-1]["route"] != route):
            routes.append({"route": route, "at": s["ts"]})
    if intervals:
        intervals[-1]["end"] = report_ts
    for i in intervals:
        i["duration_s"] = round(float(i["end"]) - float(i["start"]), 1)
    hidden = [i for i in intervals if i["state"] == "hidden"]
    return {
        "visibility": intervals,
        "routes": routes,
        "total_hidden_s": round(sum(i["duration_s"] for i in hidden), 1),
        "longest_hidden_s": max((i["duration_s"] for i in hidden), default=0.0),
    }
