from __future__ import annotations

import io
from typing import BinaryIO

from app.core.errors import NotFoundError, ProviderUnavailable
from app.core.logging import get_logger
from app.services.storage.base import Scope, StorageProvider, StoredObject, validate_key

logger = get_logger(__name__)


class S3Storage(StorageProvider):
    """S3-compatible storage (AWS S3, MinIO, Supabase Storage, R2, Wasabi)."""

    name = "s3"
    supports_native_presign = True

    def __init__(
        self,
        *,
        bucket_originals: str,
        bucket_artifacts: str,
        endpoint_url: str | None,
        region: str,
        access_key: str | None,
        secret_key: str | None,
        force_path_style: bool = True,
        server_side_encryption: str | None = None,
    ):
        import boto3
        from botocore.config import Config

        self._buckets = {
            "originals": bucket_originals,
            "artifacts": bucket_artifacts,
            "reports": bucket_artifacts,
        }
        self._prefix = {"originals": "", "artifacts": "", "reports": "reports/"}
        self.sse = server_side_encryption or None
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if force_path_style else "auto"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
            ),
        )

    def _loc(self, scope: Scope, key: str) -> tuple[str, str]:
        validate_key(key)
        return self._buckets[scope], f"{self._prefix.get(scope, '')}{key}"

    def ensure_buckets(self) -> None:
        for bucket in set(self._buckets.values()):
            try:
                self.client.head_bucket(Bucket=bucket)
            except Exception:
                try:
                    self.client.create_bucket(Bucket=bucket)
                    logger.info("s3_bucket_created", extra={"bucket": bucket})
                except Exception as exc:  # pragma: no cover
                    raise ProviderUnavailable(
                        "s3", f"Cannot access or create bucket {bucket}: {exc}"
                    ) from exc

    def write(self, scope: Scope, key: str, data: bytes, content_type: str) -> StoredObject:
        bucket, k = self._loc(scope, key)
        try:
            # SSE is opt-in: MinIO only accepts it when a KMS is configured.
            extra = {"ServerSideEncryption": self.sse} if self.sse else {}
            self.client.put_object(
                Bucket=bucket, Key=k, Body=data, ContentType=content_type, **extra
            )
        except Exception as exc:
            raise ProviderUnavailable("s3", f"Upload failed: {exc}") from exc
        return StoredObject(scope=scope, key=key, size=len(data), content_type=content_type)

    def read(self, scope: Scope, key: str) -> bytes:
        bucket, k = self._loc(scope, key)
        try:
            return self.client.get_object(Bucket=bucket, Key=k)["Body"].read()
        except self.client.exceptions.NoSuchKey:
            raise NotFoundError(f"Stored object not found: {scope}/{key}") from None
        except Exception as exc:
            raise ProviderUnavailable("s3", f"Download failed: {exc}") from exc

    def open(self, scope: Scope, key: str) -> BinaryIO:
        return io.BytesIO(self.read(scope, key))

    def exists(self, scope: Scope, key: str) -> bool:
        bucket, k = self._loc(scope, key)
        try:
            self.client.head_object(Bucket=bucket, Key=k)
            return True
        except Exception:
            return False

    def size(self, scope: Scope, key: str) -> int:
        bucket, k = self._loc(scope, key)
        try:
            return int(self.client.head_object(Bucket=bucket, Key=k)["ContentLength"])
        except Exception:
            return 0

    def delete(self, scope: Scope, key: str) -> None:
        bucket, k = self._loc(scope, key)
        try:
            self.client.delete_object(Bucket=bucket, Key=k)
        except Exception as exc:  # pragma: no cover
            logger.warning("s3_delete_failed", extra={"detail": str(exc)})

    def presign(self, scope: Scope, key: str, ttl: int) -> str | None:
        bucket, k = self._loc(scope, key)
        try:
            return self.client.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": k}, ExpiresIn=ttl
            )
        except Exception:
            return None

    def health(self) -> dict:
        try:
            self.client.list_buckets()
            return {"provider": self.name, "status": "healthy", "buckets": self._buckets}
        except Exception as exc:
            return {"provider": self.name, "status": "unhealthy", "detail": str(exc)}
