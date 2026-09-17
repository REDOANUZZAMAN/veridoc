"""Deterministic demo provider for synthetic-media indicators.

**What this is.** A transparent, reproducible feature detector. It measures eight
real properties of the raster (spectral roll-off, noise flatness, cross-channel
coupling, gradient kurtosis, provenance completeness, text-rendering regularity,
block-variance entropy, palette continuity) and combines them with fixed
published weights. Same input, same output, on every machine - no randomness
anywhere.

**What this is not.** It is not a trained synthetic-media classifier and it is
not calibrated against a labelled corpus. It exists so the product is complete
and testable without a paid detection API, and so the integration seam is real:
swap in a production model via ``AIGC_PROVIDER=remote_http`` and nothing
downstream changes.

Every result it produces is labelled ``is_demo: true`` in the API, the UI and the
PDF report.
"""
from __future__ import annotations

import numpy as np

from app.core.logging import get_logger
from app.services.aigc.base import (
    UNCERTAINTY_NOTE,
    AigcIndicator,
    AigcPageResult,
    AigcProvider,
    AigcTarget,
    band_for,
)

logger = get_logger(__name__)


def _piecewise(value: float, low: float, high: float, invert: bool = False) -> float:
    """Map a measurement onto 0..1 with a linear ramp between low and high."""
    if high == low:
        return 0.0
    t = (value - low) / (high - low)
    t = max(0.0, min(1.0, t))
    return 1.0 - t if invert else t


class DemoHeuristicAigcProvider(AigcProvider):
    key = "demo_heuristic"
    label = "Demo Heuristic Synthetic-Media Analyser"
    model_name = "veridoc-demo-heuristic"
    model_version = "0.4.0"
    is_demo = True
    disclaimer = (
        "DEMO PROVIDER - deterministic feature heuristics, not a trained synthetic-media "
        "classifier. Results are reproducible and explainable but are not calibrated against a "
        "labelled corpus. Configure a production detector before relying on this signal for a "
        "claim decision."
    )

    # Published weights - the sum is 1.0 so the likelihood stays interpretable.
    WEIGHTS = {
        "spectral_rolloff": 0.19,
        "noise_flatness": 0.17,
        "channel_coupling": 0.12,
        "gradient_kurtosis": 0.11,
        "provenance_absent": 0.13,
        "text_render_irregularity": 0.12,
        "variance_entropy": 0.09,
        "palette_continuity": 0.07,
    }

    def available(self) -> tuple[bool, str]:
        try:
            import cv2  # noqa: F401
        except Exception as exc:
            return False, f"OpenCV unavailable: {exc}"
        return True, "deterministic local heuristics"

    def analyze(self, target: AigcTarget) -> AigcPageResult:
        import cv2

        arr = np.frombuffer(target.image_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None or min(bgr.shape[:2]) < 48:
            return self._inconclusive(target, "Raster could not be decoded at analysable size.")

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h, w = gray.shape
        indicators: list[AigcIndicator] = []
        raw: dict = {}

        # 1. spectral roll-off: synthetic renders often lack fine high-frequency energy
        spectrum = np.abs(np.fft.fftshift(np.fft.fft2(gray * np.hanning(w)[None, :] *
                                                      np.hanning(h)[:, None])))
        cy, cx = h // 2, w // 2
        yy, xx = np.ogrid[:h, :w]
        radius = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        rmax = float(radius.max()) or 1.0
        total = float(spectrum.sum()) or 1.0
        high_band = float(spectrum[radius > rmax * 0.62].sum()) / total
        raw["high_frequency_energy_share"] = high_band
        indicators.append(AigcIndicator(
            "spectral_rolloff", "Spectral high-frequency share",
            high_band, _piecewise(high_band, 0.004, 0.055, invert=True),
            self.WEIGHTS["spectral_rolloff"],
            "Generative renders tend to carry less fine high-frequency energy than a sensor capture.",
        ))

        # 2. noise flatness: uniform residual variance across the frame
        residual = cv2.absdiff(gray.astype(np.uint8), cv2.medianBlur(gray.astype(np.uint8), 3))
        bh, bw = max(h // 16, 1), max(w // 16, 1)
        trimmed = residual[: bh * 16, : bw * 16].astype(np.float32)
        block_std = trimmed.reshape(bh, 16, bw, 16).std(axis=(1, 3))
        flatness = float(block_std.std() / (block_std.mean() + 1e-6))
        raw["noise_variation_coefficient"] = flatness
        indicators.append(AigcIndicator(
            "noise_flatness", "Noise-field uniformity",
            flatness, _piecewise(flatness, 0.35, 1.30, invert=True),
            self.WEIGHTS["noise_flatness"],
            "A suspiciously uniform noise field suggests the image was synthesised rather than captured.",
        ))

        # 3. cross-channel coupling of fine detail
        chans = [cv2.Laplacian(bgr[:, :, i].astype(np.float32), cv2.CV_32F).ravel()
                 for i in range(3)]
        corrs = []
        for a, b in ((0, 1), (1, 2), (0, 2)):
            sa, sb = chans[a], chans[b]
            if sa.std() > 1e-6 and sb.std() > 1e-6:
                corrs.append(abs(float(np.corrcoef(sa, sb)[0, 1])))
        coupling = float(np.mean(corrs)) if corrs else 0.0
        raw["channel_detail_correlation"] = coupling
        indicators.append(AigcIndicator(
            "channel_coupling", "Cross-channel detail correlation",
            coupling, _piecewise(coupling, 0.80, 0.995),
            self.WEIGHTS["channel_coupling"],
            "Demosaiced camera output decorrelates fine detail between colour channels; "
            "synthetic output often does not.",
        ))

        # 4. gradient kurtosis
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3).ravel()
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3).ravel()
        mag = np.sqrt(gx ** 2 + gy ** 2)
        mag = mag[mag > 1e-3]
        if mag.size > 100:
            centered = (mag - mag.mean()) / (mag.std() + 1e-6)
            kurtosis = float((centered ** 4).mean())
        else:
            kurtosis = 3.0
        raw["gradient_kurtosis"] = kurtosis
        indicators.append(AigcIndicator(
            "gradient_kurtosis", "Edge-gradient kurtosis",
            kurtosis, _piecewise(kurtosis, 60.0, 6.0),
            self.WEIGHTS["gradient_kurtosis"],
            "Document scans produce heavy-tailed gradients from crisp glyph edges; "
            "over-smooth gradient statistics are a synthetic-render trait.",
        ))

        # 5. provenance completeness
        provenance_missing = 0.0 if target.has_camera_exif else 1.0
        if target.is_lossless_render:
            # A PDF page render legitimately has no camera metadata.
            provenance_missing = 0.25
        raw["camera_provenance_present"] = target.has_camera_exif
        indicators.append(AigcIndicator(
            "provenance_absent", "Capture provenance absent",
            provenance_missing, provenance_missing, self.WEIGHTS["provenance_absent"],
            "Absent camera EXIF removes the strongest evidence that a raster came from a device; "
            "it is weak on its own because exports and messaging apps strip metadata.",
        ))

        # 6. text-rendering irregularity (document-specific)
        confs = np.array(target.ocr_confidences, dtype=float)
        heights = np.array(target.glyph_heights, dtype=float)
        if confs.size >= 12 and heights.size >= 12:
            conf_cv = float(confs.std() / (confs.mean() + 1e-6))
            height_cv = float(heights.std() / (heights.mean() + 1e-6))
            irregularity = min(conf_cv * 1.4 + height_cv, 2.0)
            note = ("Generated document imagery usually renders glyphs with inconsistent metrics "
                    "and uneven recognisability.")
        else:
            irregularity = 0.0
            note = "Too little recognised text on this page to assess glyph regularity."
        raw["text_irregularity_index"] = irregularity
        indicators.append(AigcIndicator(
            "text_render_irregularity", "Text-rendering irregularity",
            irregularity, _piecewise(irregularity, 0.30, 1.10),
            self.WEIGHTS["text_render_irregularity"], note,
        ))

        # 7. block-variance entropy
        variances = block_std.ravel()
        hist, _ = np.histogram(variances, bins=24, range=(0, max(float(variances.max()), 1e-3)))
        p = hist / max(hist.sum(), 1)
        p = p[p > 0]
        entropy = float(-(p * np.log2(p)).sum()) if p.size else 0.0
        raw["variance_entropy_bits"] = entropy
        indicators.append(AigcIndicator(
            "variance_entropy", "Block-variance entropy",
            entropy, _piecewise(entropy, 3.4, 1.2),
            self.WEIGHTS["variance_entropy"],
            "Low entropy in the distribution of local variance indicates an unnaturally "
            "homogeneous surface.",
        ))

        # 8. palette continuity
        small = cv2.resize(bgr, (min(w, 256), min(h, 256)), interpolation=cv2.INTER_AREA)
        unique_colours = int(np.unique(small.reshape(-1, 3), axis=0).shape[0])
        density = unique_colours / float(small.shape[0] * small.shape[1])
        raw["unique_colour_density"] = density
        indicators.append(AigcIndicator(
            "palette_continuity", "Colour palette density",
            density, _piecewise(density, 0.25, 0.92),
            self.WEIGHTS["palette_continuity"],
            "Continuous-tone synthetic output fills colour space more densely than a "
            "printed-document scan.",
        ))

        likelihood = float(sum(i.contribution for i in indicators))
        likelihood = max(0.0, min(0.97, likelihood))
        if target.is_lossless_render:
            # Vector-rendered pages are not photographic; damp the score so a clean
            # generated PDF page is not scored like a synthetic photograph.
            likelihood *= 0.82
        band = band_for(likelihood)
        top = sorted(indicators, key=lambda i: -i.contribution)[:3]
        summary = self._summary(band, top)

        return AigcPageResult(
            page_number=target.page_number, likelihood=likelihood, band=band,
            indicators=indicators, provider_key=self.key, provider_label=self.label,
            model_name=self.model_name, model_version=self.model_version, is_demo=True,
            disclaimer=self.disclaimer, summary=summary,
            evidence={
                "measurements": {k: (round(v, 6) if isinstance(v, float) else v)
                                 for k, v in raw.items()},
                "weights": self.WEIGHTS,
                "source_is_lossless_render": target.is_lossless_render,
                "source_mime": target.source_mime,
                "damping_applied": 0.82 if target.is_lossless_render else 1.0,
                "uncertainty_note": UNCERTAINTY_NOTE,
            },
        )

    def _summary(self, band: str, top: list[AigcIndicator]) -> str:
        drivers = ", ".join(f"{i.label.lower()} ({i.normalized:.2f})" for i in top)
        if band == "no_significant_indicators":
            return ("No significant synthetic-media indicators detected. Strongest measured "
                    f"features: {drivers}. This is not a certificate of authenticity.")
        return (f"{'Notable' if band == 'notable_indicators' else 'Potential'} synthetic-media "
                f"indicators detected, driven mainly by {drivers}. Corroborate with metadata "
                "provenance and issuer verification before drawing any conclusion.")

    def _inconclusive(self, target: AigcTarget, reason: str) -> AigcPageResult:
        return AigcPageResult(
            page_number=target.page_number, likelihood=0.0, band="no_significant_indicators",
            indicators=[], provider_key=self.key, provider_label=self.label,
            model_name=self.model_name, model_version=self.model_version, is_demo=True,
            disclaimer=self.disclaimer,
            summary=f"Analysis inconclusive: {reason}", evidence={"reason": reason},
        )
