"""DebugAssist API for the dashboard (port 8400). Read-only over runs, the decision ledger and the
sources, plus feedback; `GET /api/runs/{id}/stream` pushes live updates (server-sent events)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from debugassist.api import data
from debugassist.api.data import Paths, arr, obj

VITALS = os.environ.get("VITALS_URL", "http://localhost:8100")
BUGDROP = os.environ.get("BUGDROP_URL", "http://localhost:8200")
PHOENIX = os.environ.get("PHOENIX_URL", "http://localhost:6006")
ARTIFACT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webm": "video/webm", ".zip": "application/zip"}

app = FastAPI(title="DebugAssist API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DASHBOARD_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
PATHS = Paths()


def _state(run_id: str) -> dict[str, Any]:
    s = data.load_state(PATHS, run_id)
    if s is None:
        raise HTTPException(404, f"no run {run_id}")
    return s


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs(issue: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    return data.runs(PATHS, issue, limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    s = _state(run_id)
    return {
        "summary": data.summary(s),
        "state": s,
        "graph": data.graph(PATHS, s),
        "phoenix_url": f"{PHOENIX}/projects",
    }


@app.get("/api/runs/{run_id}/decisions")
def run_decisions(run_id: str) -> list[dict[str, Any]]:
    _state(run_id)
    return data.decisions(PATHS, run_id)


@app.get("/api/runs/{run_id}/calls")
def run_calls(run_id: str) -> list[dict[str, Any]]:
    _state(run_id)
    return data.calls(PATHS, run_id)


@app.get("/api/runs/{run_id}/artifacts")
def run_artifacts(run_id: str) -> list[dict[str, Any]]:
    """E2E screenshots, videos and traces left by the validation ladder."""
    _state(run_id)
    root = PATHS.runs / run_id / "repo" / ".da-e2e" / "test-results"
    if not root.is_dir():
        return []
    return [
        {"path": str(f.relative_to(root)), "type": ARTIFACT_TYPES[f.suffix], "bytes": f.stat().st_size}
        for f in sorted(root.rglob("*"))
        if f.suffix in ARTIFACT_TYPES
    ]


@app.get("/api/runs/{run_id}/artifacts/{path:path}")
def run_artifact(run_id: str, path: str) -> FileResponse:
    _state(run_id)
    root = (PATHS.runs / run_id / "repo" / ".da-e2e" / "test-results").resolve()
    f = (root / path).resolve()
    if root not in f.parents or not f.is_file() or f.suffix not in ARTIFACT_TYPES:
        raise HTTPException(404, "no such artifact")
    return FileResponse(f, media_type=ARTIFACT_TYPES[f.suffix])


class FeedbackIn(BaseModel):
    target: str = Field(default="rca", max_length=64)  # "rca", "claim:3", "fix", "pr"
    reaction: Literal["up", "down"]
    comment: str = Field(default="", max_length=2000)


@app.get("/api/runs/{run_id}/feedback")
def run_feedback(run_id: str) -> list[dict[str, Any]]:
    return data.feedback(PATHS, run_id)


@app.post("/api/runs/{run_id}/feedback", status_code=201)
def post_feedback(run_id: str, body: FeedbackIn, background: BackgroundTasks) -> dict[str, Any]:
    _state(run_id)
    row = data.add_feedback(PATHS, {"run_id": run_id, **body.model_dump()})
    background.add_task(_route_feedback, run_id, body.model_dump(), str(row["at"]))
    return row


async def _route_feedback(run_id: str, entry: dict[str, Any], at: str) -> None:
    """D18 in the background; the routed outcome is appended next to the feedback it answers."""
    from debugassist.pipeline import feedback, postpr

    try:
        state, _ = postpr._load(run_id)  # pyright: ignore[reportPrivateUsage]
        deps = await postpr._deps(state)  # pyright: ignore[reportPrivateUsage]
        try:
            routed = await feedback.route(state, deps, entry)
        finally:
            if deps.engine.ledger is not None:
                await deps.engine.ledger.close()
    except Exception as exc:
        routed = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    data.add_feedback(PATHS, {"run_id": run_id, "routed_for": at, "routed": routed})


# ---- post-PR tools --------------------------------------------------------------------------


class DiffFixIn(BaseModel):
    instruction: str = Field(min_length=3, max_length=500)


@app.post("/api/runs/{run_id}/diff-fix", status_code=202)
def start_diff_fix(run_id: str, body: DiffFixIn) -> dict[str, str]:
    """Start the diff fixer as a background job (minutes); poll GET …/jobs/{job}."""
    _state(run_id)
    job = uuid.uuid4().hex[:10]
    jobs = PATHS.runs / run_id / "jobs"
    jobs.mkdir(exist_ok=True)
    cli = Path(sys.executable).parent / "debugassist"
    with (jobs / f"{job}.log").open("w") as log:
        subprocess.Popen(  # noqa: S603 - fixed argv, instruction passed as one argument
            [str(cli), "fix-diff", run_id, body.instruction, "--job", job],
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=PATHS.root,
            start_new_session=True,
        )
    return {"job": job}


@app.get("/api/runs/{run_id}/jobs/{job}")
def get_job(run_id: str, job: str) -> dict[str, Any]:
    if not job.isalnum():
        raise HTTPException(404, "no such job")
    d = PATHS.runs / run_id / "jobs"
    result, log = d / f"{job}.json", d / f"{job}.log"
    if result.is_file():
        return {"status": "done", "result": json.loads(result.read_text())}
    if log.is_file():
        tail = [ln for ln in log.read_text().splitlines() if ln.strip()][-6:]
        return {"status": "running", "log": tail}
    raise HTTPException(404, "no such job")


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    correction: bool = False


@app.post("/api/runs/{run_id}/ask")
async def ask(run_id: str, body: AskIn) -> dict[str, Any]:
    from debugassist.pipeline import postpr

    _state(run_id)
    return await postpr.ask(run_id, body.message, body.session_id, correction=body.correction)


@app.get("/api/runs/{run_id}/chat")
def chat_sessions(run_id: str) -> list[dict[str, Any]]:
    from debugassist.pipeline import postpr

    _state(run_id)
    return postpr.sessions(run_id)


@app.get("/api/runs/{run_id}/chat/{session_id}")
def chat_session(run_id: str, session_id: str) -> list[dict[str, Any]]:
    from debugassist.pipeline import postpr

    _state(run_id)
    return postpr.session(run_id, session_id)


@app.post("/api/runs/{run_id}/open")
def open_in_machine(run_id: str) -> dict[str, Any]:
    from debugassist.pipeline import postpr

    _state(run_id)
    try:
        return postpr.open_env(run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/proposals")
def proposals() -> list[dict[str, Any]]:
    """Skill updates proposed by the feedback loop (local marketplace PRs awaiting a human)."""
    d = PATHS.data / "mock" / "github"
    rows = [json.loads(f.read_text()) for f in sorted(d.glob("marketplace-pr-*.json"))] if d.is_dir() else []
    return [
        {k: v for k, v in r.items() if k != "patch"}
        | {"patch_lines": len(str(r.get("patch", "")).splitlines())}
        for r in rows
    ]


def _files_snapshot(run_dir: Path) -> dict[str, int]:
    files = [run_dir / "state.json", *run_dir.glob("nodes/*.json"), *run_dir.glob("agents/*.jsonl")]
    return {str(f.relative_to(run_dir)): f.stat().st_size for f in files if f.is_file()}


async def _stream(run_id: str, interval: float = 1.0, max_idle: int = 1800) -> AsyncIterator[str]:
    """Poll the run directory; emit `graph` when nodes change and `call` for each new agent log line."""
    run_dir = PATHS.runs / run_id
    seen: dict[str, int] = {}
    offsets: dict[str, int] = {}
    idle = 0
    while idle < max_idle:
        snap = _files_snapshot(run_dir)
        if snap != seen:
            idle = 0
            for name, size in snap.items():
                if name.startswith("agents/") and size > offsets.get(name, 0):
                    with (run_dir / name).open() as f:
                        f.seek(offsets.get(name, 0))
                        chunk = f.read()
                    complete, _, _rest = chunk.rpartition("\n")
                    offsets[name] = offsets.get(name, 0) + len(complete) + (1 if complete else 0)
                    for line in complete.splitlines():
                        if line.strip():
                            yield f"event: call\ndata: {line}\n\n"
            s = data.load_state(PATHS, run_id)
            if s is not None:
                payload = {"summary": data.summary(s), "graph": data.graph(PATHS, s)}
                yield f"event: graph\ndata: {json.dumps(payload)}\n\n"
                if s.get("status") not in ("running",):
                    yield "event: end\ndata: {}\n\n"
                    return
            seen = snap
        else:
            idle += 1
            yield ": keep-alive\n\n"
        await asyncio.sleep(interval)


@app.get("/api/runs/{run_id}/stream")
async def run_stream(run_id: str) -> StreamingResponse:
    _state(run_id)
    return StreamingResponse(
        _stream(run_id), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


def _get(url: str, **params: Any) -> Any:
    try:
        return httpx.get(url, params=params, timeout=10).raise_for_status().json()
    except httpx.HTTPError:
        return None


@app.get("/api/issues")
def list_issues() -> list[dict[str, Any]]:
    """Vitals issues and BugDrop reports, each with its latest run (triage, status, outcome)."""
    latest: dict[str, dict[str, Any]] = {}
    for r in data.runs(PATHS, limit=500):
        latest.setdefault(str(r["issue_id"]), r)
    out: list[dict[str, Any]] = []
    for i in arr(_get(f"{VITALS}/api/issues", limit=100)):
        out.append(
            {
                "source": "vitals",
                "id": i["id"],
                "title": i["title"],
                "kind": i.get("kind"),
                "app": i.get("app"),
                "version": i.get("version"),
                "status": i.get("status"),
                "opened_at": i.get("opened_at"),
                "events": obj(i.get("group")).get("count"),
                "url": f"{VITALS}/issues/{i['id']}",
                "run": latest.get(i["id"]),
            }
        )
    for r in arr(_get(f"{BUGDROP}/api/reports", limit=100)):
        out.append(
            {
                "source": "bugdrop",
                "id": r["id"],
                "title": r["description"][:140],
                "kind": "bug_report",
                "app": r.get("app"),
                "version": r.get("version"),
                "status": r.get("status"),
                "opened_at": r.get("created_at"),
                "events": None,
                "url": f"{BUGDROP}/reports/{r['id']}",
                "run": latest.get(r["id"]),
            }
        )
    return sorted(out, key=lambda x: str(x.get("opened_at") or ""), reverse=True)


@app.get("/api/inbox")
def get_inbox(limit: int = 100) -> list[dict[str, Any]]:
    return data.inbox(PATHS, limit)


@app.get("/api/metrics")
def metrics() -> dict[str, Any]:
    return {"impact": data.impact(PATHS), "decisions": data.decision_quality(PATHS)}


@app.get("/api/marketplace")
def marketplace() -> dict[str, Any]:
    return data.marketplace(PATHS)


def main() -> None:
    import uvicorn

    uvicorn.run("debugassist.api.app:app", host="127.0.0.1", port=int(os.environ.get("API_PORT", "8400")))
