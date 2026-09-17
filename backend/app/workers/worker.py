"""RQ worker entry point:  python -m app.workers.worker"""
from __future__ import annotations

import sys

from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def main() -> int:
    configure_logging()
    try:
        import redis
        from rq import Worker
    except Exception as exc:  # pragma: no cover
        logger.error("rq_not_installed", extra={"detail": str(exc)})
        return 2
    try:
        connection = redis.Redis.from_url(settings.redis_url)
        connection.ping()
    except Exception as exc:
        logger.error(
            "redis_unreachable",
            extra={"url": settings.redis_url.rsplit('@', 1)[-1], "detail": str(exc)[:200]},
        )
        return 3
    logger.info("worker_starting", extra={"queue": settings.queue_name})
    Worker([settings.queue_name], connection=connection).work(with_scheduler=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
