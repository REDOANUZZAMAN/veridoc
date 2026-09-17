"""Redis/RQ job queue with a transparent in-process fallback.

``submit_analysis`` returns the mode it used. When Redis is unreachable the API
falls back to a FastAPI background task, so upload-and-analyse still works on a
laptop with no Redis - and the chosen mode is recorded on the analysis run so an
operator can see which path executed.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_QUEUE = None
_CHECKED = False


@dataclass(slots=True)
class Submission:
    mode: str                 # redis | inline
    job_id: str | None = None
    detail: str = ""

    @property
    def needs_inline_execution(self) -> bool:
        return self.mode == "inline"


def get_queue():
    global _QUEUE, _CHECKED
    if _CHECKED:
        return _QUEUE
    _CHECKED = True
    if settings.queue_mode != "redis":
        return None
    try:
        import redis
        from rq import Queue

        connection = redis.Redis.from_url(settings.redis_url, socket_timeout=1.5)
        connection.ping()
        _QUEUE = Queue(
            settings.queue_name, connection=connection,
            default_timeout=settings.analysis_timeout_seconds,
        )
        logger.info("queue_ready", extra={"queue": settings.queue_name})
    except Exception as exc:
        logger.warning("queue_unavailable_using_inline", extra={"detail": str(exc)[:160]})
        _QUEUE = None
    return _QUEUE


def reset_queue_cache() -> None:
    global _QUEUE, _CHECKED
    _QUEUE, _CHECKED = None, False


def submit_analysis(
    document_id: str, *, actor_id: str | None = None, run_id: str | None = None,
    reprocess_of: str | None = None,
) -> Submission:
    queue = get_queue()
    if queue is None:
        return Submission(mode="inline", detail="Redis unavailable or queue disabled.")
    try:
        job = queue.enqueue(
            "app.workers.tasks.analyze_document_task",
            document_id, actor_id, run_id, reprocess_of,
            job_timeout=settings.analysis_timeout_seconds,
            result_ttl=86400, failure_ttl=604800,
        )
        return Submission(mode="redis", job_id=job.id, detail=f"queued on {settings.queue_name}")
    except Exception as exc:
        logger.warning("enqueue_failed_using_inline", extra={"detail": str(exc)[:160]})
        reset_queue_cache()
        return Submission(mode="inline", detail=f"Enqueue failed: {exc}")


def queue_health() -> dict:
    queue = get_queue()
    if queue is None:
        return {"mode": "inline", "healthy": True,
                "detail": "Analysis runs in-process; no Redis worker required."}
    try:
        return {
            "mode": "redis", "healthy": True, "name": queue.name,
            "queued_jobs": queue.count,
            "failed_jobs": queue.failed_job_registry.count,
            "started_jobs": queue.started_job_registry.count,
            "workers": len(queue.connection.smembers("rq:workers")),
        }
    except Exception as exc:
        return {"mode": "redis", "healthy": False, "detail": str(exc)[:200]}
