"""Queue workers (Redis + Arq): `enqueue` puts an issue on the queue; a worker resolves its agent type and
runs the pipeline in that type's runtime container. Start one with `debugassist harness worker`."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Any, cast

from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker

from debugassist.core.policy import ROOT
from debugassist.harness import agent_types, launcher

REDIS = RedisSettings.from_dsn(
    os.environ.get("REDIS_URL")
    or f"redis://:{os.environ.get('REDIS_PASSWORD') or 'debugassist-dev'}@localhost:6379/0"
)


# Arq's default serializer is pickle, and a worker unpickles a job before it looks up the function: whoever
# can write to Redis would run code as the worker. Jobs here are strings and lists, so JSON carries them.
def dumps(job: dict[str, Any]) -> bytes:
    return json.dumps(job, default=str).encode()


def loads(raw: bytes) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(raw))


async def run_issue(
    ctx: dict[str, Any], issue_ref: str, agent_type: str | None = None, run_args: list[str] | None = None
) -> dict[str, Any]:
    info = launcher.peek(issue_ref)
    t, why = agent_types.resolve(**info, override=agent_type)
    log = ROOT / ".data" / "worker" / f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{issue_ref}.log"
    code = await asyncio.to_thread(launcher.run_in_container, t.name, issue_ref, run_args or [], log)
    return {
        "issue": issue_ref,
        "agent_type": t.name,
        "why": why,
        "exit_code": code,
        "log": str(log.relative_to(ROOT)),
    }


async def enqueue(issue_ref: str, agent_type: str | None = None, run_args: list[str] | None = None) -> str:
    pool = await create_pool(REDIS, job_serializer=dumps, job_deserializer=loads)
    try:
        job = await pool.enqueue_job("run_issue", issue_ref, agent_type, run_args or [])
        assert job is not None
        return job.job_id
    finally:
        await pool.aclose()


def make_worker(burst: bool = False) -> Worker:
    return Worker(
        functions=[run_issue],
        redis_settings=REDIS,
        burst=burst,
        job_timeout=3600,
        max_jobs=2,
        job_serializer=dumps,
        job_deserializer=loads,
    )
