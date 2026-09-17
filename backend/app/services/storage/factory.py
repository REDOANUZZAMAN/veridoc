from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.services.storage.base import StorageProvider
from app.services.storage.local import LocalStorage
from app.services.storage.s3 import S3Storage

logger = get_logger(__name__)


@lru_cache
def get_storage() -> StorageProvider:
    if settings.storage_provider == "s3":
        store = S3Storage(
            bucket_originals=settings.s3_bucket_originals,
            bucket_artifacts=settings.s3_bucket_artifacts,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key=settings.s3_access_key_id,
            secret_key=settings.s3_secret_access_key,
            force_path_style=settings.s3_force_path_style,
            server_side_encryption=settings.s3_server_side_encryption,
        )
        try:
            store.ensure_buckets()
            return store
        except Exception as exc:
            # Losing the object store must never lose an upload: fall back to the
            # local volume and shout about it loudly.
            logger.error("s3_unavailable_falling_back_to_local", extra={"detail": str(exc)})
    return LocalStorage(settings.storage_local_root)


def reset_storage_cache() -> None:
    get_storage.cache_clear()
