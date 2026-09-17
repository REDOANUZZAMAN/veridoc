from __future__ import annotations

import json
import time

from app.core.errors import ProviderUnavailable
from app.services.ocr.base import BBox, OcrPageResult, OcrProvider, OcrTarget, OcrWord
from app.services.storage.factory import get_storage


class DemoFixtureProvider(OcrProvider):
    """Deterministic OCR replay for offline demos and CI.

    It does not recognise anything: it replays a fixture that was written next to
    the document's artifacts (``<prefix>/ocr/page-N.json``). Used so the golden
    demo walkthrough is byte-identical on every machine, and so OCR tests do not
    depend on a Tesseract build. Results are labelled ``is_demo``.
    """

    key = "demo_fixture"
    label = "Demo Fixture OCR Provider (replay, no recognition)"
    version = "1.0"
    is_demo = True

    def available(self) -> tuple[bool, str]:
        return True, "replays bundled fixtures"

    def extract(self, target: OcrTarget) -> OcrPageResult:
        if not target.artifact_prefix:
            raise ProviderUnavailable("demo_fixture", "No artifact prefix supplied.")
        storage = get_storage()
        key = f"{target.artifact_prefix}/ocr/page-{target.page_number:03d}.json"
        started = time.perf_counter()
        if not storage.exists("artifacts", key):
            raise ProviderUnavailable(
                "demo_fixture", f"No OCR fixture stored for page {target.page_number}."
            )
        payload = json.loads(storage.read("artifacts", key).decode("utf-8"))
        words = [
            OcrWord(
                text=w["text"], confidence=float(w.get("confidence", 0.95)),
                bbox=BBox(**w["bbox"]), line_index=int(w.get("line", 0)),
                block_index=int(w.get("block", 0)),
            )
            for w in payload.get("words", [])
        ]
        return OcrPageResult(
            page_number=target.page_number,
            text=payload.get("text", ""), words=words,
            mean_confidence=float(payload.get("mean_confidence", 0.95)),
            provider=self.key, provider_version=self.version,
            duration_ms=int((time.perf_counter() - started) * 1000),
            status="completed", engine_detail={"route": "fixture_replay", "is_demo": True},
        )
