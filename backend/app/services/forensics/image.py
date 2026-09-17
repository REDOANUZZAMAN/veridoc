"""Image forensics.

Real measurements, no simulation:

* **JPEG profile**    - quantisation tables, estimated quality, chroma subsampling.
* **ELA**             - error level analysis against a controlled re-compression.
* **Noise residual**  - local variance of a median-filtered residual, per block.
* **Copy-move**       - ORB keypoint self-matching with offset clustering.
* **Resampling**      - periodicity of the second derivative spectrum.
* **JPEG grid**       - blockiness energy on the 8px lattice vs. off-lattice.
* **Local quality**   - per-block DCT sparsity, to expose a re-compressed patch.

Each metric is turned into a *signal*, with the measured numbers preserved as
evidence. None of them is treated as proof of manipulation on its own.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np

from app.core.logging import get_logger
from app.db.enums import FindingCategory, Severity
from app.services.forensics.base import (
    RawFinding,
    clamp,
    region,
    severity_from_confidence,
)

logger = get_logger(__name__)

DETECTOR = "image-forensics-suite"
DETECTOR_VERSION = "1.6.0"

BLOCK = 16
MIN_EDGE = 64
MIN_COPY_MOVE_MATCHES = 22
MIN_COPY_MOVE_AREA_RATIO = 0.006
# Region-scan thresholds. Two-sample z against the rest of the page, plus a
# minimum effect size so a large window cannot become significant on a trivial
# difference.
ELA_REGION_Z = 7.0
ELA_MIN_EFFECT = 0.40
NOISE_REGION_Z = 9.5
NOISE_MIN_EFFECT = 0.60
GHOST_REGION_Z = 7.0
GHOST_MIN_EFFECT = 0.45
RESAMPLING_PEAK_THRESHOLD = 20.0
BLOCKINESS_Z_THRESHOLD = 4.0
TEXT_DOMINANCE_LIMIT = 0.35


@dataclass(slots=True)
class ImageForensicReport:
    findings: list[RawFinding] = field(default_factory=list)
    features: dict = field(default_factory=dict)
    artifacts: dict[str, bytes] = field(default_factory=dict)
    suspect_regions: list[dict] = field(default_factory=list)
    error: str | None = None


def decode(image_bytes: bytes) -> np.ndarray | None:
    import cv2

    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return img


def jpeg_profile(image_bytes: bytes) -> dict:
    """Quantisation tables tell us how (and how often) a JPEG was compressed."""
    from PIL import Image

    out: dict = {"is_jpeg": False}
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            out["format"] = img.format
            if img.format != "JPEG":
                return out
            out["is_jpeg"] = True
            out["progressive"] = bool(img.info.get("progressive"))
            out["subsampling"] = img.info.get("subsampling")
            tables = getattr(img, "quantization", {}) or {}
            out["table_count"] = len(tables)
            luma = tables.get(0)
            if luma is not None:
                arr = np.array(luma, dtype=float)
                out["luma_dc"] = float(arr[0])
                out["luma_mean"] = float(arr.mean())
                out["estimated_quality"] = _quality_from_table(arr)
                out["table_is_standard"] = bool(_is_standard_table(arr))
    except Exception as exc:  # pragma: no cover
        out["error"] = f"{type(exc).__name__}"
    return out


_STD_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
], dtype=float)


def _quality_from_table(table: np.ndarray) -> float:
    """Invert the IJG scaling law to recover the quality factor."""
    t = table.flatten()[:64]
    std = _STD_LUMA[: len(t)]
    ratios = t / np.maximum(std, 1e-6)
    scale = float(np.median(ratios)) * 100.0
    if scale <= 0:
        return 100.0
    quality = (200.0 - scale) / 2.0 if scale >= 100 else 5000.0 / scale
    return round(float(np.clip(quality, 1, 100)), 1)


def _is_standard_table(table: np.ndarray) -> bool:
    t = table.flatten()[:64]
    ratios = t / np.maximum(_STD_LUMA[: len(t)], 1e-6)
    return bool(np.std(ratios) < 0.08)


def error_level_analysis(bgr: np.ndarray, quality: int = 90) -> tuple[np.ndarray, np.ndarray]:
    import cv2

    ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG re-encode failed during ELA")
    recompressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(bgr, recompressed).astype(np.float32)
    magnitude = diff.max(axis=2)
    peak = float(magnitude.max()) or 1.0
    scaled = np.clip(magnitude * (255.0 / peak), 0, 255).astype(np.uint8)
    heatmap = cv2.applyColorMap(scaled, cv2.COLORMAP_INFERNO)
    return magnitude, heatmap


def block_means(channel: np.ndarray, block: int = BLOCK) -> np.ndarray:
    h, w = channel.shape[:2]
    bh, bw = h // block, w // block
    if bh < 2 or bw < 2:
        return np.zeros((0, 0), dtype=np.float32)
    trimmed = channel[: bh * block, : bw * block]
    return trimmed.reshape(bh, block, bw, block).mean(axis=(1, 3)).astype(np.float32)


def robust_z(grid: np.ndarray) -> np.ndarray:
    if grid.size == 0:
        return grid
    median = float(np.median(grid))
    mad = float(np.median(np.abs(grid - median))) or 1e-6
    return (grid - median) / (1.4826 * mad)


def cluster_blocks(
    mask: np.ndarray, block: int, *, scale: float = 1.0, min_blocks: int = 3
) -> list[dict]:
    """Connected-component clustering of flagged blocks into pixel-space regions."""
    import cv2

    if mask.size == 0 or not mask.any():
        return []
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    out = []
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        if area < min_blocks:
            continue
        out.append({
            "region": region(
                int(x * block * scale), int(y * block * scale),
                int(w * block * scale), int(h * block * scale),
            ),
            "block_count": int(area),
        })
    out.sort(key=lambda r: -r["block_count"])
    return out


def content_mask(gray: np.ndarray, block: int = BLOCK, min_std: float = 3.0) -> np.ndarray:
    """Blocks that actually contain content.

    Scanned and photographed documents are mostly blank paper. Blank blocks have
    almost no signal, so their ELA response, noise residual and DCT sparsity are
    dominated by quantisation floor rather than by document history - including
    them in a z-score makes every text block look like an outlier. Every metric
    below is therefore computed over content blocks only.
    """

    h, w = gray.shape[:2]
    bh, bw = h // block, w // block
    if bh < 2 or bw < 2:
        return np.zeros((0, 0), dtype=bool)
    trimmed = gray[: bh * block, : bw * block].astype(np.float32)
    tiles = trimmed.reshape(bh, block, bw, block)
    std = tiles.std(axis=(1, 3))
    return std >= min_std


def masked_robust_z(grid: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Robust z-scores computed from content blocks only, zero elsewhere."""
    out = np.zeros_like(grid, dtype=np.float32)
    if grid.size == 0 or mask.size != grid.size or not mask.any():
        return out
    values = grid[mask]
    if values.size < 8:
        return out
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median))) or 1e-6
    out[mask] = (grid[mask] - median) / (1.4826 * mad)
    return out


def region_scan(
    grid: np.ndarray,
    mask: np.ndarray,
    *,
    block: int,
    scale: float = 1.0,
    window: int = 6,
    stride: int = 3,
    min_content_blocks: int = 12,
    z_threshold: float = 6.0,
    min_effect: float = 0.35,
) -> list[dict]:
    """Find contiguous regions whose metric differs from the rest of the page.

    Per-block z-scores are the wrong instrument here. A document's blocks
    legitimately vary enormously - a block of body text, a block of blank paper
    and a block of logo behave nothing alike - so a single block is never a
    significant outlier, and thresholding blocks either misses real edits or
    floods the report.

    What *is* significant is a contiguous area whose mean differs from the rest
    of the page. This slides a window over the block grid and runs a two-sample
    comparison for each position:

        z = (window_mean - rest_mean) / (rest_std / sqrt(n_window))

    A window is reported only when it is both statistically strong (|z| above
    ``z_threshold``) and materially different (effect size above ``min_effect``
    in units of the page's own standard deviation), which keeps large windows
    from becoming significant on a trivial difference. Overlapping hits are
    merged into one region.
    """
    if grid.size == 0 or mask.shape != grid.shape or mask.sum() < min_content_blocks * 3:
        return []
    rows, cols = grid.shape
    window = max(2, min(window, rows, cols))
    stride = max(1, min(stride, window))
    hits: list[dict] = []

    for r in range(0, max(rows - window + 1, 1), stride):
        for c in range(0, max(cols - window + 1, 1), stride):
            win_mask = np.zeros_like(mask)
            win_mask[r:r + window, c:c + window] = True
            inside = mask & win_mask
            n_inside = int(inside.sum())
            if n_inside < min_content_blocks:
                continue
            outside = mask & ~win_mask
            if int(outside.sum()) < min_content_blocks:
                continue
            inside_values = grid[inside]
            outside_values = grid[outside]
            rest_std = float(outside_values.std())
            if rest_std < 1e-6:
                continue
            delta = float(inside_values.mean() - outside_values.mean())
            z = delta / (rest_std / np.sqrt(n_inside))
            effect = abs(delta) / rest_std
            if abs(z) < z_threshold or effect < min_effect:
                continue
            hits.append({
                "row": r, "col": c, "rows": window, "cols": window,
                "z": round(float(z), 2), "effect_size": round(effect, 3),
                "content_blocks": n_inside,
                "window_mean": round(float(inside_values.mean()), 4),
                "page_mean": round(float(outside_values.mean()), 4),
                "direction": "elevated" if z > 0 else "suppressed",
            })

    if not hits:
        return []
    # Merge overlapping windows of the same direction into single regions.
    hits.sort(key=lambda h: -abs(h["z"]))
    merged: list[dict] = []
    for hit in hits:
        r0, c0 = hit["row"], hit["col"]
        r1, c1 = r0 + hit["rows"], c0 + hit["cols"]
        for existing in merged:
            if existing["direction"] != hit["direction"]:
                continue
            er0, ec0 = existing["row"], existing["col"]
            er1, ec1 = er0 + existing["rows"], ec0 + existing["cols"]
            if not (r1 <= er0 or er1 <= r0 or c1 <= ec0 or ec1 <= c0):
                existing["row"], existing["col"] = min(er0, r0), min(ec0, c0)
                existing["rows"] = max(er1, r1) - existing["row"]
                existing["cols"] = max(ec1, c1) - existing["col"]
                existing["z"] = max(existing["z"], hit["z"], key=abs)
                existing["content_blocks"] = max(existing["content_blocks"],
                                                 hit["content_blocks"])
                existing["windows_merged"] = existing.get("windows_merged", 1) + 1
                break
        else:
            merged.append({**hit, "windows_merged": 1})

    for item in merged:
        item["region"] = region(
            int(item["col"] * block * scale), int(item["row"] * block * scale),
            int(item["cols"] * block * scale), int(item["rows"] * block * scale),
        )
    return merged


def noise_residual_profile(gray: np.ndarray) -> tuple[np.ndarray, dict]:
    import cv2

    smoothed = cv2.medianBlur(gray, 3)
    residual = cv2.absdiff(gray, smoothed).astype(np.float32)
    grid = block_means(residual)
    mask = content_mask(gray)
    stats = {}
    if grid.size and mask.size == grid.size and mask.any():
        values = grid[mask]
        mean = float(values.mean())
        stats = {
            "block_mean": round(mean, 4),
            "block_std": round(float(values.std()), 4),
            "coefficient_of_variation": round(float(values.std() / (mean + 1e-6)), 4),
            "content_blocks": int(mask.sum()),
            "blocks": int(grid.size),
        }
    return grid, stats


def copy_move_matches(gray: np.ndarray) -> dict:
    """ORB self-matching: near-duplicate keypoints separated in space."""
    import cv2

    h, w = gray.shape[:2]
    diag = float(np.hypot(h, w))
    orb = cv2.ORB_create(nfeatures=2500, scaleFactor=1.2, edgeThreshold=12)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    if descriptors is None or len(keypoints) < 40:
        return {"keypoints": 0 if descriptors is None else len(keypoints), "clusters": []}

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    knn = matcher.knnMatch(descriptors, descriptors, k=3)
    min_separation = max(0.03 * diag, 24.0)
    offsets: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {}
    for group in knn:
        for m in group:
            if m.queryIdx == m.trainIdx or m.distance > 24:
                continue
            p, q = keypoints[m.queryIdx].pt, keypoints[m.trainIdx].pt
            dx, dy = q[0] - p[0], q[1] - p[1]
            if np.hypot(dx, dy) < min_separation:
                continue
            bucket = (int(round(dx / 8.0)), int(round(dy / 8.0)))
            canonical = bucket if bucket >= (0, 0) else (-bucket[0], -bucket[1])
            offsets.setdefault(canonical, []).append(
                (int(p[0]), int(p[1]), int(q[0]), int(q[1]))
            )

    # Printed documents repeat glyphs constantly, which produces many small
    # matched groups at unrelated offsets. A genuine copy-move leaves a large,
    # contiguous group sharing one displacement - so require both a high match
    # count and a region of meaningful size.
    page_area = float(h * w)
    clusters = []
    for bucket, pts in offsets.items():
        if len(pts) < MIN_COPY_MOVE_MATCHES:
            continue
        xs = [p[0] for p in pts] + [p[2] for p in pts]
        ys = [p[1] for p in pts] + [p[3] for p in pts]
        box_w, box_h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        if (box_w * box_h) / page_area < MIN_COPY_MOVE_AREA_RATIO:
            continue
        clusters.append({
            "match_count": len(pts),
            "offset": [bucket[0] * 8, bucket[1] * 8],
            "bbox": region(min(xs), min(ys), box_w, box_h),
            "area_ratio": round((box_w * box_h) / page_area, 5),
            "sample_pairs": pts[:6],
        })
    clusters.sort(key=lambda c: -c["match_count"])
    return {"keypoints": len(keypoints), "clusters": clusters[:5],
            "offset_groups": len(offsets),
            "thresholds": {"min_matches": MIN_COPY_MOVE_MATCHES,
                           "min_area_ratio": MIN_COPY_MOVE_AREA_RATIO,
                           "max_descriptor_distance": 24}}


def text_dominance(gray: np.ndarray) -> float:
    """How much of the raster is regularly-spaced lines of print.

    The resampling detector looks for periodicity in the second-derivative
    spectrum. Printed text produces exactly such periodicity from its line
    pitch, so on a document image the metric is not diagnostic. Quantifying text
    dominance lets the signal be suppressed where it cannot discriminate, rather
    than reported on every page.
    """
    import cv2

    try:
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_per_row = (binary > 0).mean(axis=1)
        text_rows = float((ink_per_row > 0.02).mean())
        if text_rows <= 0.01:
            return 0.0
        profile = ink_per_row - ink_per_row.mean()
        spectrum = np.abs(np.fft.rfft(profile * np.hanning(profile.size)))
        spectrum[0] = 0.0
        if spectrum.size < 8:
            return text_rows
        periodicity = float(spectrum[2:].max() / (np.median(spectrum[2:]) + 1e-6))
        return float(min(1.0, text_rows * min(periodicity / 20.0, 1.0) * 2.5))
    except Exception:
        return 0.0


def resampling_score(gray: np.ndarray) -> dict:
    """Interpolation leaves a periodic trace in the second-derivative spectrum."""
    import cv2

    small = gray.astype(np.float32)
    if min(small.shape) > 1200:
        scale = 1200.0 / min(small.shape)
        small = cv2.resize(small, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    lap = cv2.Laplacian(small, cv2.CV_32F, ksize=3)
    out = {}
    for axis, name in ((1, "horizontal"), (0, "vertical")):
        profile = np.abs(lap).mean(axis=axis)
        profile = profile - profile.mean()
        if profile.size < 64:
            continue
        spectrum = np.abs(np.fft.rfft(profile * np.hanning(profile.size)))
        spectrum[0] = 0.0
        if spectrum.size < 8:
            continue
        peak_idx = int(np.argmax(spectrum[2:])) + 2
        peak = float(spectrum[peak_idx])
        median = float(np.median(spectrum[2:])) or 1e-6
        out[name] = {
            "peak_ratio": round(peak / median, 3),
            "peak_period_px": round(profile.size / max(peak_idx, 1), 2),
        }
    ratios = [v["peak_ratio"] for v in out.values()] or [0.0]
    out["max_peak_ratio"] = round(max(ratios), 3)
    return out


def jpeg_grid_score(gray: np.ndarray) -> dict:
    """Compare pixel-difference energy on the 8px JPEG lattice vs. off-lattice."""
    g = gray.astype(np.float32)
    dx = np.abs(np.diff(g, axis=1))
    dy = np.abs(np.diff(g, axis=0))
    if dx.size == 0 or dy.size == 0:
        return {}
    on_x = dx[:, 7::8].mean() if dx.shape[1] > 8 else 0.0
    off_x = np.delete(dx, np.arange(7, dx.shape[1], 8), axis=1).mean()
    on_y = dy[7::8, :].mean() if dy.shape[0] > 8 else 0.0
    off_y = np.delete(dy, np.arange(7, dy.shape[0], 8), axis=0).mean()
    return {
        "grid_energy_ratio": round(float(((on_x + on_y) / 2) / (((off_x + off_y) / 2) + 1e-6)), 4),
        "on_lattice": round(float((on_x + on_y) / 2), 4),
        "off_lattice": round(float((off_x + off_y) / 2), 4),
    }


GHOST_QUALITIES = (30, 40, 50, 60, 70, 80, 88, 94)


def jpeg_ghost_map(bgr: np.ndarray, block: int = BLOCK) -> tuple[np.ndarray, dict]:
    """Per-block estimate of the quality a region was last compressed at.

    The image is re-compressed at a ladder of qualities. For each block, the
    quality whose re-compression error is smallest is the quality that block is
    already sitting at - a JPEG is close to a fixed point of its own quantiser.
    The result is a map of *compression history* rather than of content, so it is
    far less confounded by ink density than a raw coefficient statistic: a patch
    saved at quality 20 and pasted into a quality 88 photograph shows up as a
    contiguous area of low estimated quality.
    """
    import cv2

    h, w = bgr.shape[:2]
    bh, bw = h // block, w // block
    if bh < 3 or bw < 3:
        return np.zeros((0, 0), dtype=np.float32), {}

    errors = []
    for quality in GHOST_QUALITIES:
        ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            continue
        again = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        diff = cv2.absdiff(bgr, again).astype(np.float32).mean(axis=2)
        errors.append(block_means(diff, block))
    if not errors:
        return np.zeros((0, 0), dtype=np.float32), {}

    stack = np.stack(errors, axis=0)                     # (quality, rows, cols)
    best = np.argmin(stack, axis=0)
    ladder = np.array(GHOST_QUALITIES[: stack.shape[0]], dtype=np.float32)
    grid = ladder[best]
    return grid, {
        "quality_ladder": list(GHOST_QUALITIES[: stack.shape[0]]),
        "modal_quality": float(np.bincount(best.ravel()).argmax()
                               and ladder[np.bincount(best.ravel()).argmax()]),
        "median_estimated_quality": float(np.median(grid)),
        "blocks": int(grid.size),
    }


def blockiness_grid(gray: np.ndarray, block: int = BLOCK) -> tuple[np.ndarray, dict]:
    """Per-block JPEG blocking energy.

    A region that was compressed hard and then pasted in keeps the blocking
    artefacts of *its own* encoding. Measuring lattice-aligned gradient energy
    per block therefore localises a splice even when the host image was later
    re-saved at a higher quality, which is exactly the case a global
    quality estimate misses.
    """
    g = gray.astype(np.float32)
    h, w = g.shape[:2]
    bh, bw = h // block, w // block
    if bh < 3 or bw < 3:
        return np.zeros((0, 0), dtype=np.float32), {}
    dx = np.abs(np.diff(g, axis=1, append=g[:, -1:]))
    dy = np.abs(np.diff(g, axis=0, append=g[-1:, :]))
    lattice_x = np.zeros(w, dtype=bool)
    lattice_x[7::8] = True
    lattice_y = np.zeros(h, dtype=bool)
    lattice_y[7::8] = True
    grid = np.zeros((bh, bw), dtype=np.float32)
    for by in range(bh):
        ys = slice(by * block, (by + 1) * block)
        for bx in range(bw):
            xs = slice(bx * block, (bx + 1) * block)
            tile_x, tile_y = dx[ys, xs], dy[ys, xs]
            mx = lattice_x[xs]
            my = lattice_y[ys]
            on_energy = 0.0
            off_energy = 0.0
            if mx.any() and (~mx).any():
                on_energy += float(tile_x[:, mx].mean())
                off_energy += float(tile_x[:, ~mx].mean())
            if my.any() and (~my).any():
                on_energy += float(tile_y[my, :].mean())
                off_energy += float(tile_y[~my, :].mean())
            grid[by, bx] = on_energy / (off_energy + 1e-6)
    mask = content_mask(gray, block=block)
    values = grid[mask] if mask.shape == grid.shape and mask.any() else grid
    return grid, {
        "mean_lattice_ratio": round(float(values.mean()), 4) if values.size else 0.0,
        "std_lattice_ratio": round(float(values.std()), 4) if values.size else 0.0,
        "content_blocks": int(mask.sum()) if mask.shape == grid.shape else int(grid.size),
    }


def local_quality_grid(gray: np.ndarray) -> tuple[np.ndarray, dict]:
    """Per-8x8-block DCT sparsity - a proxy for how hard that block was compressed."""
    import cv2

    h, w = gray.shape[:2]
    bh, bw = h // 8, w // 8
    if bh < 4 or bw < 4:
        return np.zeros((0, 0), dtype=np.float32), {}
    g = gray[: bh * 8, : bw * 8].astype(np.float32) - 128.0
    blocks = g.reshape(bh, 8, bw, 8).transpose(0, 2, 1, 3).reshape(-1, 8, 8)
    sparsity = np.empty(blocks.shape[0], dtype=np.float32)
    for i, block in enumerate(blocks):
        coeffs = np.abs(cv2.dct(block))
        high = coeffs[2:, 2:]
        sparsity[i] = float((high < 1.0).mean())
    grid = sparsity.reshape(bh, bw)
    mask = content_mask(gray, block=8)
    values = grid[mask] if mask.shape == grid.shape and mask.any() else grid
    return grid, {
        "mean_high_freq_sparsity": round(float(values.mean()), 4),
        "std_high_freq_sparsity": round(float(values.std()), 4),
        "content_blocks": int(mask.sum()) if mask.shape == grid.shape else int(grid.size),
        "blocks": int(grid.size),
    }


def analyze_raster(
    image_bytes: bytes,
    *,
    page: int,
    origin: str = "page_render",
    coord_scale: float = 1.0,
    is_lossless_render: bool = False,
) -> ImageForensicReport:
    """Run the full suite over one raster.

    ``coord_scale`` maps this raster's pixel space onto the page render space used
    by the viewer, so every reported region is directly clickable.
    """
    import cv2

    report = ImageForensicReport()
    bgr = None
    try:
        bgr = decode(image_bytes)
    except Exception as exc:
        report.error = f"decode_failed:{type(exc).__name__}"
    if bgr is None:
        report.error = report.error or "decode_failed"
        return report
    if min(bgr.shape[:2]) < MIN_EDGE:
        report.error = "raster_too_small"
        report.features["dimensions"] = {"width": int(bgr.shape[1]), "height": int(bgr.shape[0])}
        return report

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    report.features["dimensions"] = {"width": int(bgr.shape[1]), "height": int(bgr.shape[0])}
    report.features["origin"] = origin

    profile = jpeg_profile(image_bytes)
    report.features["jpeg"] = profile

    # --- ELA -----------------------------------------------------------------
    try:
        magnitude, heatmap = error_level_analysis(bgr)
        ok, png = cv2.imencode(".png", heatmap)
        if ok:
            report.artifacts["ela"] = png.tobytes()
        grid = block_means(magnitude)
        content = content_mask(gray)
        regions = region_scan(
            grid, content, block=BLOCK, scale=coord_scale,
            z_threshold=ELA_REGION_Z, min_effect=ELA_MIN_EFFECT,
        )
        content_values = grid[content] if content.any() else grid
        report.features["ela"] = {
            "block_mean": round(float(content_values.mean()), 4) if content_values.size else 0.0,
            "block_p99": (round(float(np.percentile(content_values, 99)), 4)
                          if content_values.size else 0.0),
            "content_blocks": int(content.sum()),
            "total_blocks": int(grid.size),
            "regions_flagged": len(regions),
            "strongest_z": max((abs(r["z"]) for r in regions), default=0.0),
            "region_z_threshold": ELA_REGION_Z,
            "source_is_lossless": is_lossless_render,
            "method": ("sliding-window two-sample comparison over content blocks "
                       "(blank paper excluded)"),
        }
        for hit in regions[:3]:
            direction = hit["direction"]
            confidence = clamp(
                0.5 + min(abs(hit["z"]) / 60.0, 0.2) + min(hit["effect_size"] / 3.0, 0.16),
                0.42, 0.9,
            ) * (0.8 if is_lossless_render else 1.0)
            report.suspect_regions.append({
                "source": "ela", "region": hit["region"], "page": page,
                "confidence": confidence, "block_count": hit["content_blocks"],
            })
            report.findings.append(RawFinding(
                code="IMG_ELA_LOCAL_ANOMALY", category=FindingCategory.FORENSICS,
                severity=severity_from_confidence(confidence),
                title=f"Localised compression-response anomaly ({direction}) on page {page}",
                description=(
                    "Error level analysis shows a contiguous area whose response to controlled "
                    "re-compression differs from the rest of the page content at "
                    f"z = {hit['z']} (effect size {hit['effect_size']} standard deviations, "
                    f"measured over {hit['content_blocks']} content blocks). "
                    + ("The area responds *more* strongly than its surroundings, which happens "
                       "when content was edited and re-saved at a higher quality than the host "
                       "image. "
                       if direction == "elevated" else
                       "The area responds *less* strongly than its surroundings, which happens "
                       "when the content was already compressed more heavily before it was "
                       "placed here. ")
                    + "Legitimately different content - a logo, a photograph, a pre-printed "
                      "block - can also behave this way."
                    + (" The source here is a lossless render, which weakens this signal."
                       if is_lossless_render else "")
                ),
                confidence=confidence, detector=DETECTOR, model_version=DETECTOR_VERSION,
                page=page, region=hit["region"],
                evidence={"metric": "error_level_analysis", "direction": direction,
                          "z": hit["z"], "effect_size": hit["effect_size"],
                          "window_mean": hit["window_mean"], "page_mean": hit["page_mean"],
                          "content_blocks": hit["content_blocks"], "origin": origin,
                          **{k: v for k, v in report.features["ela"].items()
                             if k in {"method", "content_blocks", "source_is_lossless"}}},
                recommendation="Open the ELA layer in the viewer and compare with the original.",
                extras={"signal_group": "image"},
            ))
    except Exception as exc:
        logger.warning("ela_failed", extra={"detail": str(exc)[:160]})
        report.features["ela"] = {"error": type(exc).__name__}

    # --- noise residual -------------------------------------------------------
    try:
        noise_grid, noise_stats = noise_residual_profile(gray)
        report.features["noise"] = noise_stats
        if noise_grid.size:
            content = content_mask(gray)
            regions = region_scan(
                noise_grid, content, block=BLOCK, scale=coord_scale,
                z_threshold=NOISE_REGION_Z, min_effect=NOISE_MIN_EFFECT,
            )
            report.features["noise"]["regions_flagged"] = len(regions)
            for hit in regions[:2]:
                confidence = clamp(
                    0.45 + min(abs(hit["z"]) / 70.0, 0.18) + min(hit["effect_size"] / 3.0, 0.14),
                    0.4, 0.82,
                )
                report.suspect_regions.append({
                    "source": "noise", "region": hit["region"], "page": page,
                    "confidence": confidence, "block_count": hit["content_blocks"],
                })
                report.findings.append(RawFinding(
                    code="IMG_NOISE_INCONSISTENCY", category=FindingCategory.FORENSICS,
                    severity=severity_from_confidence(confidence, Severity.MEDIUM),
                    title=f"Sensor-noise inconsistency on page {page}",
                    description=(
                        "The local noise floor in this area differs from the rest of the page at "
                        f"z = {hit['z']} (effect size {hit['effect_size']}). A single capture "
                        "device and a single processing path normally leave a consistent noise "
                        "signature; content brought in from another source keeps its own."
                    ),
                    confidence=confidence, detector=DETECTOR, model_version=DETECTOR_VERSION,
                    page=page, region=hit["region"],
                    evidence={"metric": "noise_residual", "z": hit["z"],
                              "effect_size": hit["effect_size"],
                              "window_mean": hit["window_mean"], "page_mean": hit["page_mean"],
                              **noise_stats},
                    extras={"signal_group": "image"},
                ))
    except Exception as exc:
        report.features["noise"] = {"error": type(exc).__name__}

    # --- copy-move ------------------------------------------------------------
    try:
        cm = copy_move_matches(gray)
        report.features["copy_move"] = {
            "keypoints": cm["keypoints"], "cluster_count": len(cm["clusters"]),
            "clusters": [{k: v for k, v in c.items() if k != "sample_pairs"} for c in cm["clusters"]],
        }
        for cluster in cm["clusters"][:2]:
            confidence = clamp(0.48 + min(cluster["match_count"], 80) / 200.0, 0.48, 0.88)
            scaled = region(
                int(cluster["bbox"]["x"] * coord_scale), int(cluster["bbox"]["y"] * coord_scale),
                int(cluster["bbox"]["width"] * coord_scale),
                int(cluster["bbox"]["height"] * coord_scale),
            )
            report.suspect_regions.append({
                "source": "copy_move", "region": scaled, "page": page,
                "confidence": confidence, "block_count": cluster["match_count"],
            })
            report.findings.append(RawFinding(
                code="IMG_COPY_MOVE_REGION", category=FindingCategory.FORENSICS,
                severity=severity_from_confidence(confidence),
                title=f"Duplicated image region on page {page}",
                description=(f"{cluster['match_count']} keypoint pairs repeat with a consistent "
                             f"displacement of {cluster['offset']} pixels, which is the signature "
                             "of a region copied and pasted within the same page. Repeating "
                             "template graphics can also produce this pattern."),
                confidence=confidence, detector=DETECTOR, model_version=DETECTOR_VERSION,
                page=page, region=scaled,
                evidence={"metric": "orb_copy_move", "match_count": cluster["match_count"],
                          "offset_px": cluster["offset"], "keypoints": cm["keypoints"],
                          "sample_pairs": cluster["sample_pairs"]},
                recommendation="Check whether the duplicated area covers a value or a signature.",
                extras={"signal_group": "image"},
            ))
    except Exception as exc:
        report.features["copy_move"] = {"error": type(exc).__name__}

    # --- resampling & JPEG lattice -------------------------------------------
    try:
        rs = resampling_score(gray)
        text_like = text_dominance(gray)
        rs["text_dominance"] = text_like
        rs["signal_suppressed_for_text"] = text_like >= TEXT_DOMINANCE_LIMIT
        report.features["resampling"] = rs
        ratio = rs.get("max_peak_ratio", 0.0)
        if ratio > RESAMPLING_PEAK_THRESHOLD and text_like < TEXT_DOMINANCE_LIMIT:
            confidence = clamp(0.40 + min(ratio, 60.0) / 140.0, 0.40, 0.72)
            report.findings.append(RawFinding(
                code="IMG_RESAMPLING_ARTIFACTS", category=FindingCategory.FORENSICS,
                severity=severity_from_confidence(confidence, Severity.MEDIUM),
                title=f"Resampling periodicity detected on page {page}",
                description=("The second-derivative spectrum has a strong periodic peak, the trace "
                             "left by interpolation when content is rescaled or rotated. Two "
                             "benign causes produce the same peak: whole-page rescaling during "
                             "scanning, and the regular line pitch of printed text. Treat as "
                             "context unless it coincides with another signal."),
                confidence=confidence, detector=DETECTOR, model_version=DETECTOR_VERSION,
                page=page, evidence={"metric": "resampling_periodicity", **rs},
                extras={"signal_group": "image"},
            ))
    except Exception as exc:
        report.features["resampling"] = {"error": type(exc).__name__}

    try:
        report.features["jpeg_grid"] = jpeg_grid_score(gray)
    except Exception as exc:
        report.features["jpeg_grid"] = {"error": type(exc).__name__}

    # --- compression history (JPEG ghost) -------------------------------------
    try:
        q_grid, q_stats = local_quality_grid(gray)
        # Kept as context: informative in aggregate, but too confounded by ink
        # density to threshold region-by-region on a text document.
        report.features["local_quality"] = {**q_stats, "used_as_signal": False,
                                            "note": ("aggregate context only - per-region "
                                                     "thresholding of coefficient sparsity is "
                                                     "dominated by ink density on text pages")}
        if profile.get("is_jpeg"):
            ghost, ghost_stats = jpeg_ghost_map(bgr)
            content = content_mask(gray)
            regions = []
            if ghost.size and content.shape == ghost.shape:
                regions = region_scan(
                    ghost, content, block=BLOCK, scale=coord_scale, window=5, stride=2,
                    min_content_blocks=10, z_threshold=GHOST_REGION_Z,
                    min_effect=GHOST_MIN_EFFECT,
                )
            report.features["jpeg_ghost"] = {
                **ghost_stats, "regions_flagged": len(regions),
                "region_z_threshold": GHOST_REGION_Z,
            }
            for hit in [r for r in regions if r["direction"] == "suppressed"][:2]:
                confidence = clamp(
                    0.54 + min(abs(hit["z"]) / 50.0, 0.22) + min(hit["effect_size"] / 3.0, 0.14),
                    0.5, 0.9,
                )
                report.suspect_regions.append({
                    "source": "jpeg_ghost", "region": hit["region"], "page": page,
                    "confidence": confidence, "block_count": hit["content_blocks"],
                })
                report.findings.append(RawFinding(
                    code="IMG_COMPRESSION_INCONSISTENCY", category=FindingCategory.FORENSICS,
                    severity=severity_from_confidence(confidence),
                    title=f"Region carries a different compression history on page {page}",
                    description=(
                        "Re-compressing the image across a ladder of qualities shows that this "
                        f"area last sat at an estimated quality of {hit['window_mean']:.0f}, "
                        f"against {hit['page_mean']:.0f} for the rest of the page "
                        f"(z = {hit['z']}, effect size {hit['effect_size']}, "
                        f"{hit['content_blocks']} content blocks). Content compressed elsewhere "
                        "and then placed into this image keeps its own quantisation, which is "
                        "what this measures. An embedded photograph or a low-quality logo "
                        "produces the same reading."
                    ),
                    confidence=confidence, detector=DETECTOR, model_version=DETECTOR_VERSION,
                    page=page, region=hit["region"],
                    evidence={"metric": "jpeg_ghost_quality_map",
                              "estimated_region_quality": hit["window_mean"],
                              "estimated_page_quality": hit["page_mean"],
                              "z": hit["z"], "effect_size": hit["effect_size"],
                              "content_blocks": hit["content_blocks"], **ghost_stats},
                    recommendation=("Ask the claimant for the unedited original capture and "
                                    "compare this region."),
                    extras={"signal_group": "image"},
                ))
        else:
            report.features["jpeg_ghost"] = {
                "status": "not_applicable",
                "reason": ("compression-history recovery needs a JPEG source; this raster is "
                           f"{profile.get('format', 'lossless')}"),
            }
    except Exception as exc:
        report.features["jpeg_ghost"] = {"error": type(exc).__name__}

    # --- local blocking-artefact inconsistency --------------------------------
    try:
        b_grid, b_stats = blockiness_grid(gray)
        text_like = report.features.get("resampling", {}).get(
            "text_dominance", text_dominance(gray))
        b_stats["text_dominance"] = round(text_like, 3)
        # Printed strokes dominate lattice-energy measurements, so on a
        # text-heavy raster this metric cannot discriminate a pasted region from
        # ordinary type. It is recorded as context and not raised as a signal.
        b_stats["signal_suppressed_for_text"] = text_like >= TEXT_DOMINANCE_LIMIT
        report.features["blockiness"] = b_stats
        if b_grid.size and text_like < TEXT_DOMINANCE_LIMIT:
            content_b = content_mask(gray)
            if content_b.shape == b_grid.shape:
                zb = masked_robust_z(b_grid, content_b)
                mask_b = (zb > BLOCKINESS_Z_THRESHOLD) & content_b
                clusters = cluster_blocks(mask_b, BLOCK, scale=coord_scale, min_blocks=4)
                if clusters:
                    cluster = clusters[0]
                    confidence = clamp(
                        0.5 + min(float(zb.max()) / 20.0, 0.2)
                        + min(cluster["block_count"] / 60.0, 0.15), 0.5, 0.86)
                    report.suspect_regions.append({
                        "source": "blockiness", "region": cluster["region"], "page": page,
                        "confidence": confidence, "block_count": cluster["block_count"],
                    })
                    report.findings.append(RawFinding(
                        code="IMG_LOCAL_BLOCKINESS_ANOMALY",
                        category=FindingCategory.FORENSICS,
                        severity=severity_from_confidence(confidence),
                        title=f"Localised JPEG blocking artefacts on page {page}",
                        description=(
                            "Gradient energy on the 8-pixel JPEG lattice is concentrated in one "
                            f"contiguous area (robust z-score {float(zb.max()):.2f}) rather than "
                            "spread across the page. A region that was compressed hard elsewhere "
                            "and then placed into this image keeps the blocking pattern of its "
                            "own encoding, which is what this measures. Strong rectangular "
                            "graphics can also raise lattice energy locally."
                        ),
                        confidence=confidence, detector=DETECTOR,
                        model_version=DETECTOR_VERSION, page=page, region=cluster["region"],
                        evidence={"metric": "local_jpeg_lattice_energy", **b_stats,
                                  "max_z": round(float(zb.max()), 2),
                                  "flagged_blocks": int(mask_b.sum()),
                                  "z_threshold": BLOCKINESS_Z_THRESHOLD,
                                  "block_count": cluster["block_count"]},
                        recommendation=("Compare this region against the surrounding content in "
                                        "the viewer's forensic layers."),
                        extras={"signal_group": "image"},
                    ))
    except Exception as exc:
        report.features["blockiness"] = {"error": type(exc).__name__}

    # --- JPEG profile signals -------------------------------------------------
    if profile.get("is_jpeg"):
        quality = profile.get("estimated_quality")
        if quality is not None and quality < 62:
            report.findings.append(RawFinding(
                code="IMG_LOW_JPEG_QUALITY", category=FindingCategory.FORENSICS,
                severity=Severity.LOW,
                title=f"Low JPEG quality ({quality}) limits forensic resolution",
                description=("Heavy compression destroys the fine detail that manipulation "
                             "detection relies on. Findings for this page carry reduced weight, "
                             "and an absence of findings should not be read as evidence of "
                             "authenticity."),
                confidence=0.6, detector=DETECTOR, model_version=DETECTOR_VERSION, page=page,
                evidence={"estimated_quality": quality, "luma_dc": profile.get("luma_dc")},
                recommendation="Request a higher-resolution original from the claimant.",
                extras={"signal_group": "image"},
            ))
        if profile.get("table_is_standard") is False:
            report.findings.append(RawFinding(
                code="IMG_NONSTANDARD_QUANT_TABLE", category=FindingCategory.FORENSICS,
                severity=Severity.LOW,
                title="Non-standard JPEG quantisation table",
                description=("The quantisation table does not follow the standard IJG scaling "
                             "curve, which points at a specific editor or converter rather than "
                             "a camera or scanner pipeline."),
                confidence=0.5, detector=DETECTOR, model_version=DETECTOR_VERSION, page=page,
                evidence={k: v for k, v in profile.items() if k != "error"},
                extras={"signal_group": "image"},
            ))
    return report
