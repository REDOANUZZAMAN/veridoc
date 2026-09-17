from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import BinaryIO

from app.core.errors import NotFoundError
from app.services.storage.base import Scope, StorageProvider, StoredObject, validate_key


class LocalStorage(StorageProvider):
    """Filesystem storage for local development and single-node installs.

    Layout mirrors the S3 bucket split so switching providers needs no key
    rewriting. Original files are written 0o440 and never re-opened for write.
    """

    name = "local"

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        for scope in ("originals", "artifacts", "reports"):
            (self.root / scope).mkdir(parents=True, exist_ok=True)

    def _path(self, scope: Scope, key: str) -> Path:
        validate_key(key)
        p = (self.root / scope / key).resolve()
        if not str(p).startswith(str(self.root / scope)):
            raise ValueError("Resolved path escapes the storage root.")
        return p

    def write(self, scope: Scope, key: str, data: bytes, content_type: str) -> StoredObject:
        p = self._path(scope, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
        if scope == "originals":
            os.chmod(p, 0o440)  # evidence: read-only once landed
        return StoredObject(
            scope=scope, key=key, size=len(data), content_type=content_type,
            checksum=hashlib.sha256(data).hexdigest(),
        )

    def read(self, scope: Scope, key: str) -> bytes:
        p = self._path(scope, key)
        if not p.exists():
            raise NotFoundError(f"Stored object not found: {scope}/{key}")
        return p.read_bytes()

    def open(self, scope: Scope, key: str) -> BinaryIO:
        p = self._path(scope, key)
        if not p.exists():
            raise NotFoundError(f"Stored object not found: {scope}/{key}")
        return open(p, "rb")

    def exists(self, scope: Scope, key: str) -> bool:
        return self._path(scope, key).exists()

    def size(self, scope: Scope, key: str) -> int:
        p = self._path(scope, key)
        return p.stat().st_size if p.exists() else 0

    def delete(self, scope: Scope, key: str) -> None:
        p = self._path(scope, key)
        if p.exists():
            os.chmod(p, 0o600)
            p.unlink()

    def delete_prefix(self, scope: Scope, prefix: str) -> int:
        base = self._path(scope, prefix)
        if base.is_dir():
            count = sum(1 for _ in base.rglob("*") if _.is_file())
            shutil.rmtree(base, ignore_errors=True)
            return count
        return 0

    def health(self) -> dict:
        try:
            probe = self.root / "artifacts" / ".health"
            probe.write_text("ok")
            probe.unlink()
            free = shutil.disk_usage(self.root).free
            return {"provider": self.name, "status": "healthy", "root": str(self.root),
                    "free_bytes": free}
        except Exception as exc:  # pragma: no cover
            return {"provider": self.name, "status": "unhealthy", "detail": str(exc)}
