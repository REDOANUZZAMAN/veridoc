from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO, Literal

Scope = Literal["originals", "artifacts", "reports"]

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,500}$")


def validate_key(key: str) -> str:
    """Reject traversal and control characters before a key ever touches disk/S3."""
    if not key or ".." in key or key.startswith("/") or not _SAFE_KEY.match(key):
        raise ValueError(f"Unsafe storage key: {key!r}")
    return key


@dataclass(slots=True)
class StoredObject:
    scope: str
    key: str
    size: int
    content_type: str
    checksum: str | None = None


class StorageProvider(ABC):
    """Object storage abstraction.

    Two logical buckets are always kept apart:
      * ``originals``  - the exact bytes the claimant uploaded. Write-once.
      * ``artifacts``  - derived renders, ELA maps, overlays, generated reports.

    Derived data can be regenerated and purged independently of evidence, which
    is what makes retention and secure deletion tractable.
    """

    name: str = "abstract"
    supports_native_presign: bool = False

    @abstractmethod
    def write(self, scope: Scope, key: str, data: bytes, content_type: str) -> StoredObject: ...

    @abstractmethod
    def read(self, scope: Scope, key: str) -> bytes: ...

    @abstractmethod
    def open(self, scope: Scope, key: str) -> BinaryIO: ...

    @abstractmethod
    def exists(self, scope: Scope, key: str) -> bool: ...

    @abstractmethod
    def delete(self, scope: Scope, key: str) -> None: ...

    @abstractmethod
    def size(self, scope: Scope, key: str) -> int: ...

    def presign(self, scope: Scope, key: str, ttl: int) -> str | None:
        """Native pre-signed URL, when the backend offers one."""
        return None

    def health(self) -> dict:
        return {"provider": self.name, "status": "unknown"}
