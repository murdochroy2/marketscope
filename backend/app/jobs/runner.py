"""In-process background job runner.

Market creation is minutes of rate-limited API work, so it cannot run inside the HTTP
request. Jobs run as asyncio tasks in the API process, and all durable state lives in the
``discovery_runs`` table. The table, not the task, is the source of truth for progress,
and runs left "running" by a crash are marked failed on the next startup.

A production deployment would put a durable queue here (arq, Celery, SQS). The pipeline
function takes plain ids, so it moves to a worker process without changes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def submit(self, job: Coroutine[Any, Any, Any], *, name: str) -> None:
        task = asyncio.create_task(job, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("job %s crashed", task.get_name(), exc_info=exc)

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
