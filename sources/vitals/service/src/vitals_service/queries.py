"""Read models: crash-rate distributions, time series, releases."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from vitals_service.db import AppSession, Event, Group
from vitals_service.ingest import version_key

DIMENSIONS = ("version", "os", "browser", "device", "city", "locale")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _sessions_in_window(db: DbSession, group: Group) -> list[AppSession]:
    start = _aware(group.first_seen) - timedelta(hours=1)
    end = _aware(group.last_seen) + timedelta(minutes=5)
    rows = db.scalars(
        select(AppSession).where(
            AppSession.app == group.app, AppSession.started_at >= start, AppSession.started_at <= end
        )
    ).all()
    return list(rows)


def _value(s: AppSession, dim: str) -> str:
    if dim.startswith("flag:"):
        v = (s.flags or {}).get(dim[5:])
        return "unknown" if v is None else str(v).lower()
    return str(getattr(s, dim) or "unknown")


def distribution(db: DbSession, group: Group, dim: str) -> dict[str, Any]:
    """Affected vs all sessions per value of `dim` (version/os/…/flag:<name>) over the group's window."""
    sessions = _sessions_in_window(db, group)
    affected_ids = set(
        db.scalars(select(Event.session_id).where(Event.fingerprint == group.fingerprint)).all()
    ) - {None}
    totals: Counter[str] = Counter()
    affected: Counter[str] = Counter()
    for s in sessions:
        v = _value(s, dim)
        totals[v] += 1
        if s.id in affected_ids:
            affected[v] += 1
    n_aff = sum(affected.values())
    n_all = sum(totals.values())
    rows = [
        {
            "value": v,
            "sessions": totals[v],
            "affected_sessions": affected[v],
            "rate": round(affected[v] / totals[v], 4) if totals[v] else 0.0,
            "share_of_sessions": round(totals[v] / n_all, 4) if n_all else 0.0,
            "share_of_affected": round(affected[v] / n_aff, 4) if n_aff else 0.0,
        }
        for v in sorted(totals, key=lambda k: -totals[k])
    ]
    return {"dimension": dim, "total_sessions": n_all, "affected_sessions": n_aff, "values": rows}


def flag_exposure(db: DbSession, group: Group) -> list[dict[str, Any]]:
    """For every flag seen in the window: exposure among all sessions vs among affected sessions."""
    sessions = _sessions_in_window(db, group)
    names = sorted({k for s in sessions for k in (s.flags or {})})
    out: list[dict[str, Any]] = []
    for name in names:
        d = distribution(db, group, f"flag:{name}")
        on = next((r for r in d["values"] if r["value"] == "true"), None)
        out.append(
            {
                "flag": name,
                "exposed_share_of_sessions": on["share_of_sessions"] if on else 0.0,
                "exposed_share_of_affected": on["share_of_affected"] if on else 0.0,
                "rate_exposed": on["rate"] if on else 0.0,
                "rate_unexposed": next((r["rate"] for r in d["values"] if r["value"] == "false"), 0.0),
            }
        )
    return out


def timeseries(db: DbSession, fingerprint: str, bucket_s: int = 300) -> list[dict[str, Any]]:
    rows = db.execute(select(Event.ts, Event.version).where(Event.fingerprint == fingerprint)).all()
    buckets: dict[int, Counter[str]] = defaultdict(Counter)
    for ts, version in rows:
        b = int(_aware(ts).timestamp()) // bucket_s * bucket_s
        buckets[b][version] += 1
    return [
        {
            "bucket": datetime.fromtimestamp(b, UTC).isoformat(),
            "count": sum(c.values()),
            "by_version": dict(c),
        }
        for b, c in sorted(buckets.items())
    ]


def releases(db: DbSession, app: str) -> list[dict[str, Any]]:
    rows = db.execute(select(AppSession.version, AppSession.started_at).where(AppSession.app == app)).all()
    stats: dict[str, dict[str, Any]] = {}
    for version, started in rows:
        s = stats.setdefault(
            version, {"version": version, "sessions": 0, "first_seen": started, "last_seen": started}
        )
        s["sessions"] += 1
        s["first_seen"] = min(_aware(s["first_seen"]), _aware(started))
        s["last_seen"] = max(_aware(s["last_seen"]), _aware(started))
    total = sum(s["sessions"] for s in stats.values()) or 1
    out = sorted(stats.values(), key=lambda s: version_key(s["version"]))
    for s in out:
        s["adoption"] = round(s["sessions"] / total, 4)
        s["first_seen"] = s["first_seen"].isoformat()
        s["last_seen"] = s["last_seen"].isoformat()
    return out
