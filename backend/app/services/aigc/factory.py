from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.services.aigc.base import AigcProvider
from app.services.aigc.heuristic_demo import DemoHeuristicAigcProvider
from app.services.aigc.remote_http import RemoteHttpAigcProvider

logger = get_logger(__name__)

REGISTRY: dict[str, type[AigcProvider]] = {
    "demo_heuristic": DemoHeuristicAigcProvider,
    "remote_http": RemoteHttpAigcProvider,
}


def get_aigc_provider(key: str | None = None) -> AigcProvider:
    resolved = key or _from_db() or settings.aigc_provider
    provider = REGISTRY.get(resolved, DemoHeuristicAigcProvider)()
    ok, detail = provider.available()
    if not ok and resolved != "demo_heuristic":
        # Falling back is explicit and logged; the demo label travels with the
        # result so a report can never imply a production model ran.
        logger.warning(
            "aigc_provider_unavailable_falling_back",
            extra={"requested": resolved, "detail": detail},
        )
        return DemoHeuristicAigcProvider()
    return provider


def _from_db() -> str | None:
    try:
        from sqlalchemy import select

        from app.db.models.config import ProviderConfig
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            return db.execute(
                select(ProviderConfig.key).where(
                    ProviderConfig.kind == "aigc", ProviderConfig.is_active.is_(True)
                )
            ).scalar_one_or_none()
    except Exception:
        return None


def list_aigc_providers() -> list[dict]:
    return [cls().describe() for cls in REGISTRY.values()]
