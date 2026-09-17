"""Storage isolation, signed URLs and error handling contracts."""
from __future__ import annotations

import pytest

from app.core.errors import (
    AppError,
    CorruptDocument,
    NotFoundError,
    ProviderUnavailable,
    RateLimited,
)
from app.core.ratelimit import parse_rate
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    sha256_bytes,
    sign_resource,
    verify_password,
    verify_resource_signature,
)
from app.services.storage.base import validate_key
from app.services.storage.local import LocalStorage


def test_storage_keys_reject_traversal(tmp_path):
    storage = LocalStorage(str(tmp_path))
    for bad in ("../escape.pdf", "/etc/passwd", "a/../../b.pdf", ""):
        with pytest.raises(ValueError):
            validate_key(bad)
        with pytest.raises(ValueError):
            storage.write("originals", bad, b"x", "application/pdf")


def test_originals_and_artifacts_are_separated(tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.write("originals", "2026/09/DOC-1/original.pdf", b"%PDF-1.7", "application/pdf")
    storage.write("artifacts", "2026/09/DOC-1/pages/page-001.png", b"png", "image/png")
    assert storage.exists("originals", "2026/09/DOC-1/original.pdf")
    assert not storage.exists("artifacts", "2026/09/DOC-1/original.pdf")
    assert (tmp_path / "originals").is_dir() and (tmp_path / "artifacts").is_dir()


def test_original_is_written_read_only(tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.write("originals", "x/original.pdf", b"%PDF-1.7", "application/pdf")
    path = tmp_path / "originals" / "x" / "original.pdf"
    assert not (path.stat().st_mode & 0o222), "evidence must not stay writable"


def test_artifacts_can_be_purged_without_touching_originals(tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.write("originals", "p/original.pdf", b"%PDF", "application/pdf")
    storage.write("artifacts", "p/pages/page-001.png", b"png", "image/png")
    removed = storage.delete_prefix("artifacts", "p")
    assert removed == 1
    assert storage.exists("originals", "p/original.pdf")


def test_missing_object_raises_not_found(tmp_path):
    storage = LocalStorage(str(tmp_path))
    with pytest.raises(NotFoundError):
        storage.read("originals", "nothing/here.pdf")


def test_signed_resource_round_trip():
    signed = sign_resource("doc-1", "original", "user-1", ttl=60)
    verify_resource_signature("doc-1", "original", "user-1", signed["exp"], signed["nonce"],
                              signed["sig"])


def test_signature_is_bound_to_resource_purpose_and_user():
    signed = sign_resource("doc-1", "original", "user-1", ttl=60)
    from app.core.errors import AuthenticationError

    for args in (("doc-2", "original", "user-1"), ("doc-1", "page_render", "user-1"),
                 ("doc-1", "original", "user-2")):
        with pytest.raises(AuthenticationError):
            verify_resource_signature(*args, signed["exp"], signed["nonce"], signed["sig"])


def test_expired_signature_is_rejected():
    from app.core.errors import AuthenticationError

    signed = sign_resource("doc-1", "original", "user-1", ttl=-5)
    with pytest.raises(AuthenticationError):
        verify_resource_signature("doc-1", "original", "user-1", signed["exp"],
                                  signed["nonce"], signed["sig"])


def test_password_hashing_is_salted_and_verifiable():
    first, second = hash_password("Str0ng!Password1"), hash_password("Str0ng!Password1")
    assert first != second
    assert verify_password("Str0ng!Password1", first)
    assert not verify_password("wrong", first)


def test_token_type_is_enforced():
    from app.core.errors import AuthenticationError

    access, _ = create_token("user-1", "admin", "access")
    assert decode_token(access, "access")["role"] == "admin"
    with pytest.raises(AuthenticationError):
        decode_token(access, "refresh")


def test_sha256_is_stable():
    assert sha256_bytes(b"veridoc") == sha256_bytes(b"veridoc")
    assert len(sha256_bytes(b"veridoc")) == 64


def test_rate_spec_parsing():
    assert parse_rate("300/minute") == (300, 60)
    assert parse_rate("10/second") == (10, 1)
    assert parse_rate("5/hour") == (5, 3600)


def test_error_payloads_carry_a_code_and_retryability():
    assert CorruptDocument().payload()["error"]["code"] == "corrupt_document"
    assert ProviderUnavailable("ocr").payload()["error"]["retryable"] is True
    assert RateLimited().payload()["error"]["retryable"] is True
    assert AppError("generic").payload()["error"]["retryable"] is False


def test_provider_unavailable_names_the_provider():
    error = ProviderUnavailable("aigc_remote_http", "endpoint timed out")
    assert error.provider == "aigc_remote_http"
    assert "timed out" in error.message


def test_validation_errors_are_structured(client):
    response = client.post("/api/auth/login", json={"email": "not-an-email"})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_failed"
    assert isinstance(body["details"], list)


def test_security_headers_are_present(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in response.headers
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-request-id"]


def test_document_bytes_are_never_cacheable(client, investigator_token, invoice_pdf,
                                            claims_token, make_claim):
    from tests.conftest import auth, upload

    data, mime = invoice_pdf
    claim = make_claim()
    document = upload(client, claims_token, data, "cache.pdf", mime, claim["id"],
                      analyze=False).json()["document"]
    response = client.get(f"/api/documents/{document['id']}/file",
                          headers=auth(investigator_token))
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
