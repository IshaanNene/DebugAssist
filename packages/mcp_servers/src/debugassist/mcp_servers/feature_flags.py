"""feature-flags MCP server (Unleash): flags, rollouts, flag↔crash correlation, gated rollback."""

from __future__ import annotations

import math
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from debugassist.core.policy import PolicyGate, Verdict
from debugassist.mcp_servers.common import env, with_evidence

mcp = FastMCP("feature-flags", log_level="WARNING")
UNLEASH = env("UNLEASH_URL", "http://localhost:4242")
VITALS = env("VITALS_URL", "http://localhost:8100")
ADMIN = {"Authorization": env("UNLEASH_ADMIN_TOKEN", "*:*.unleash-insecure-admin-api-token")}
PROJECT, ENV_NAME = "default", "development"
_http = httpx.Client(timeout=15)


def _strategies(flag: str) -> list[dict[str, Any]]:
    r = _http.get(
        f"{UNLEASH}/api/admin/projects/{PROJECT}/features/{flag}/environments/{ENV_NAME}/strategies",
        headers=ADMIN,
    )
    r.raise_for_status()
    return r.json()


def _rollout(strategies: list[dict[str, Any]]) -> int | None:
    s = next((s for s in strategies if s["name"] == "flexibleRollout"), None)
    return int(s["parameters"]["rollout"]) if s else None


@mcp.tool()
def list_flags() -> dict[str, Any]:
    """All feature flags with type, enabled state and gradual-rollout percentage."""
    feats = _http.get(f"{UNLEASH}/api/admin/projects/{PROJECT}/features", headers=ADMIN).json()["features"]
    rows: list[dict[str, Any]] = []
    for f in feats:
        envs: list[dict[str, Any]] = f.get("environments", [])
        env_state: dict[str, Any] = next((e for e in envs if e["name"] == ENV_NAME), None) or {}
        rows.append(
            {
                "name": f["name"],
                "description": f.get("description"),
                "type": f.get("type"),
                "enabled": env_state.get("enabled"),
                "rollout_pct": _rollout(_strategies(f["name"])),
            }
        )
    return with_evidence("flags", "flags", {"flags": rows})


@mcp.tool()
def get_flag(flag: str) -> dict[str, Any]:
    """A flag's strategies (rollout %, stickiness, constraints)."""
    strategies = _strategies(flag)
    return with_evidence(
        "flags", "flag", {"flag": flag, "rollout_pct": _rollout(strategies), "strategies": strategies}
    )


@mcp.tool()
def rollout_history(flag: str, limit: int = 20) -> dict[str, Any]:
    """Recent changes to a flag (who changed what, when)."""
    r = _http.get(f"{UNLEASH}/api/admin/events/{flag}", headers=ADMIN)
    events: list[dict[str, Any]] = r.json().get("events", []) if r.status_code == 200 else []
    rows: list[dict[str, Any]] = []
    for e in events[:limit]:
        data: dict[str, Any] = e.get("data") or {}
        params: dict[str, Any] = data.get("parameters", {})
        rows.append(
            {
                "at": e.get("createdAt"),
                "type": e.get("type"),
                "by": e.get("createdBy"),
                "rollout": params.get("rollout"),
            }
        )
    return with_evidence("flags", "rollout_history", {"flag": flag, "events": rows})


def two_proportion_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    """z statistic and two-sided p-value for p1 = x1/n1 vs p2 = x2/n2."""
    if min(n1, n2) == 0:
        return 0.0, 1.0
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) or 1e-12
    z = (x1 / n1 - x2 / n2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


@mcp.tool()
def flag_crash_correlation(fingerprint: str, flag: str) -> dict[str, Any]:
    """Crash rate in flag-exposed vs unexposed sessions for a Vitals group, with a two-proportion z-test."""
    d = _http.get(f"{VITALS}/api/groups/{fingerprint}/distribution", params={"by": f"flag:{flag}"}).json()
    rows = {r["value"]: r for r in d["values"]}
    on, off = rows.get("true", {}), rows.get("false", {})
    x1, n1 = on.get("affected_sessions", 0), on.get("sessions", 0)
    x2, n2 = off.get("affected_sessions", 0), off.get("sessions", 0)
    z, pval = two_proportion_z(x1, n1, x2, n2)
    total_aff = max(1, x1 + x2)
    return with_evidence(
        "flags",
        "flag_correlation",
        {
            "flag": flag,
            "fingerprint": fingerprint,
            "exposed": {"sessions": n1, "affected": x1, "rate": round(x1 / n1, 4) if n1 else None},
            "unexposed": {"sessions": n2, "affected": x2, "rate": round(x2 / n2, 4) if n2 else None},
            "share_of_affected_exposed": round(x1 / total_aff, 4),
            "z": round(z, 3),
            "p_value": pval,
            "significant": pval < 0.01 and x1 >= 3,
        },
    )


@mcp.tool()
def rollback_flag(flag: str, to_percent: int = 0, reason: str = "", dry_run: bool = True) -> dict[str, Any]:
    """Roll a flag's gradual rollout back (write; policy-gated, dry-run by default)."""
    gate = PolicyGate(mode=os.environ.get("DEBUGASSIST_MODE", "autonomous"))
    verdict = gate.verdict("flags.rollback")
    strategies = _strategies(flag)
    current = _rollout(strategies)
    effective = "dry_run" if dry_run or verdict is not Verdict.LIVE else "live"
    result: dict[str, Any] = {
        "flag": flag,
        "from_percent": current,
        "to_percent": to_percent,
        "verdict": verdict.value,
        "applied": False,
    }
    if effective == "live":
        s = next(s for s in strategies if s["name"] == "flexibleRollout")
        params = {**s["parameters"], "rollout": str(to_percent)}
        _http.put(
            f"{UNLEASH}/api/admin/projects/{PROJECT}/features/{flag}/environments/{ENV_NAME}/strategies/{s['id']}",
            headers=ADMIN,
            json={"name": "flexibleRollout", "parameters": params, "constraints": s.get("constraints", [])},
        ).raise_for_status()
        result["applied"] = True
    gate.record(
        "flags.rollback",
        Verdict(effective) if effective == "live" else Verdict.DRY_RUN,
        run_id=os.environ.get("DEBUGASSIST_RUN_ID"),
        detail={"flag": flag, "to": to_percent, "reason": reason},
        result=result,
    )
    return with_evidence("flags", "rollback", result)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
