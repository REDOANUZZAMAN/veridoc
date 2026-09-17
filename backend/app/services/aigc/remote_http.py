"""Production seam for a hosted synthetic-media detector.

Expects a JSON API of the shape::

    POST {AIGC_REMOTE_URL}
    Authorization: Bearer {AIGC_REMOTE_API_KEY}
    multipart/form-data: file=<image>, page=<int>

    200 {
      "likelihood": 0.0-1.0,
      "model": "vendor-model-name",
      "model_version": "2026.03",
      "indicators": [{"key","label","score","weight","note"}],
      "regions": [{"x","y","width","height","score"}]
    }

Any non-200, timeout or malformed body raises ``ProviderUnavailable`` so the
pipeline degrades the stage instead of fabricating a score.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.errors import ProviderUnavailable
from app.core.logging import get_logger
from app.services.aigc.base import (
    AigcIndicator,
    AigcPageResult,
    AigcProvider,
    AigcTarget,
    band_for,
)

logger = get_logger(__name__)


class RemoteHttpAigcProvider(AigcProvider):
    key = "remote_http"
    label = "Remote synthetic-media detection API"
    model_name = "remote"
    model_version = "unknown"
    is_demo = False
    disclaimer = ""

    def __init__(self, url: str | None = None, api_key: str | None = None, timeout: float = 30.0):
        self.url = url or settings.aigc_remote_url
        self.api_key = api_key or settings.aigc_remote_api_key
        self.timeout = timeout

    def available(self) -> tuple[bool, str]:
        if not self.url:
            return False, "AIGC_REMOTE_URL is not configured."
        if not self.api_key:
            return False, "AIGC_REMOTE_API_KEY is not configured."
        return True, f"configured endpoint {self.url}"

    def analyze(self, target: AigcTarget) -> AigcPageResult:
        ok, detail = self.available()
        if not ok:
            raise ProviderUnavailable("aigc_remote_http", detail)
        import httpx

        try:
            response = httpx.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (f"page-{target.page_number}.png", target.image_bytes, "image/png")},
                data={"page": str(target.page_number),
                      "document_type": target.document_type or ""},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ProviderUnavailable(
                "aigc_remote_http", f"Detection endpoint did not respond usably: {exc}"
            ) from exc

        try:
            likelihood = float(payload["likelihood"])
        except (KeyError, TypeError, ValueError):
            raise ProviderUnavailable(
                "aigc_remote_http", "Response did not contain a numeric 'likelihood'."
            ) from None
        likelihood = max(0.0, min(1.0, likelihood))
        indicators = [
            AigcIndicator(
                key=str(i.get("key", f"indicator_{n}")), label=str(i.get("label", "Indicator")),
                measured=float(i.get("score", 0.0)), normalized=float(i.get("score", 0.0)),
                weight=float(i.get("weight", 0.0)), note=str(i.get("note", "")),
            )
            for n, i in enumerate(payload.get("indicators", []) or [])
        ]
        band = band_for(likelihood)
        return AigcPageResult(
            page_number=target.page_number, likelihood=likelihood, band=band,
            indicators=indicators, provider_key=self.key,
            provider_label=str(payload.get("provider_label", self.label)),
            model_name=str(payload.get("model", "remote")),
            model_version=str(payload.get("model_version", "unknown")),
            is_demo=False, disclaimer="",
            summary=str(payload.get("summary") or
                        ("Potential synthetic-media indicators detected."
                         if likelihood >= 0.5 else
                         "No significant synthetic-media indicators detected.")),
            evidence={"endpoint": self.url, "raw": {k: v for k, v in payload.items()
                                                    if k != "indicators"}},
            region_hints=[
                {"x": int(r.get("x", 0)), "y": int(r.get("y", 0)),
                 "width": int(r.get("width", 0)), "height": int(r.get("height", 0)),
                 "unit": "render_px", "score": float(r.get("score", 0.0))}
                for r in payload.get("regions", []) or []
            ],
        )
