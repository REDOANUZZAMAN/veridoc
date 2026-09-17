"""Production seam for real insurer / registry APIs.

One adapter covers every request type; the endpoint and credential are supplied
per provider from configuration. Responses are mapped into the same
``VerificationResponse`` contract as the demo providers, with
``is_demo_data=False`` and no disclaimer.
"""
from __future__ import annotations

import time

from app.core.config import settings
from app.core.errors import ProviderUnavailable
from app.db.enums import VerificationOutcome
from app.services.verification.base import (
    VerificationCheck,
    VerificationProvider,
    VerificationQuery,
    VerificationResponse,
    outcome_from_checks,
)


class RemoteHttpVerificationProvider(VerificationProvider):
    key = "remote_http"
    label = "Production Verification API"
    mode = "production"
    request_types = ("policy_lookup", "provider_lookup", "invoice_lookup", "identity_lookup",
                     "vehicle_lookup", "payment_lookup")
    description = ("Calls a configured upstream verification endpoint. Requires "
                   "VERIFICATION_REMOTE_URL and VERIFICATION_REMOTE_API_KEY.")

    def __init__(self, url: str | None = None, api_key: str | None = None, timeout: float = 20.0):
        self.url = url or settings.verification_remote_url
        self.api_key = api_key or settings.verification_remote_api_key
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        if not self.url:
            return False, "VERIFICATION_REMOTE_URL is not configured."
        if not self.api_key:
            return False, "VERIFICATION_REMOTE_API_KEY is not configured."
        return True, f"configured endpoint {self.url}"

    def verify(self, query: VerificationQuery) -> VerificationResponse:
        ok, detail = self.available()
        if not ok:
            raise ProviderUnavailable("verification_remote_http", detail)
        import httpx

        started = time.perf_counter()
        try:
            response = httpx.post(
                self.url.rstrip("/") + f"/{query.request_type}",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"payload": query.payload, "document_id": query.document_id,
                      "claim_id": query.claim_id},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            raise ProviderUnavailable(
                "verification_remote_http", f"Upstream verification failed: {exc}"
            ) from exc

        checks = [
            VerificationCheck(
                key=str(c.get("key", f"check_{i}")), label=str(c.get("label", "Check")),
                expected=None if c.get("expected") is None else str(c["expected"]),
                actual=None if c.get("actual") is None else str(c["actual"]),
                passed=c.get("passed"), note=str(c.get("note", "")),
            )
            for i, c in enumerate(body.get("checks", []) or [])
        ]
        outcome = body.get("outcome") or outcome_from_checks(
            checks, found=bool(body.get("found", True))
        )
        if outcome not in set(VerificationOutcome):
            outcome = VerificationOutcome.PARTIAL_MATCH
        return VerificationResponse(
            outcome=outcome,
            summary=str(body.get("summary", "Upstream verification completed.")),
            checks=checks, raw=body,
            latency_ms=int((time.perf_counter() - started) * 1000),
            reference_id=body.get("reference_id"), is_demo_data=False, disclaimer="",
        )
