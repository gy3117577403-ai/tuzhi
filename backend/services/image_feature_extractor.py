from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2  # type: ignore
import numpy as np
from PIL import Image

_COLOR_NAMES = [
    ("blue", np.array([40, 80, 180])),
    ("black", np.array([25, 25, 28])),
    ("grey", np.array([140, 140, 145])),
    ("white", np.array([230, 230, 235])),
    ("red", np.array([200, 50, 50])),
]


def _nearest_color_name(bgr: np.ndarray) -> str:
    best = "grey"
    best_d = 1e9
    for name, ref in _COLOR_NAMES:
        d = float(np.linalg.norm(bgr.astype(float) - ref.astype(float)))
        if d < best_d:
            best_d = d
            best = name
    return best


def extract_image_features(image_path: str | Path) -> dict[str, Any]:
    path = Path(image_path)
    img_bgr = cv2.imread(str(path))
    if img_bgr is None:
        pil = Image.open(path).convert("RGB")
        img_rgb = np.array(pil)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(blurred, 48, 148)

    dominant = _nearest_color_name(np.mean(img_bgr.reshape(-1, 3), axis=0))

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bbox = {"x": 0, "y": 0, "w": w, "h": h}
    if contours:
        c = max(contours, key=cv2.contourArea)
        x, y, bw, bh = cv2.boundingRect(c)
        bbox = {"x": int(x), "y": int(y), "w": int(bw), "h": int(bh)}

    aspect = float(bbox["w"]) / max(float(bbox["h"]), 1.0)
    area = float(bbox["w"] * bbox["h"])
    rect_area = area if area > 0 else 1.0
    cnt_area = 0.0
    if contours:
        c = max(contours, key=cv2.contourArea)
        cnt_area = float(cv2.contourArea(c))
    rectangularity = min(1.0, (4 * cnt_area) / max((w * h), 1.0) * 0.5 + 0.3)

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=int(min(w, h) * 0.08),
        param1=50,
        param2=28,
        minRadius=max(3, int(min(w, h) * 0.02)),
        maxRadius=int(min(w, h) * 0.18),
    )
    cavity_candidates: list[dict[str, Any]] = []
    if circles is not None:
        for cx, cy, r in np.round(circles[0]).astype(int):
            cavity_candidates.append({"cx": int(cx), "cy": int(cy), "radius_px": int(r)})

    top_dual = np.mean(edges[: int(h * 0.22), :]) > np.mean(edges) * 0.9 and np.mean(edges[: int(h * 0.22), :]) > 12
    front_shroud = np.mean(edges[int(h * 0.55) :, :]) > np.mean(edges) * 0.85
    side_latch = np.mean(edges[:, : int(w * 0.18)]) > 18 or np.mean(edges[:, int(w * 0.82) :]) > 18

    warnings = [
        "Image-based dimensions are approximate and require manual confirmation.",
        "Do not use as manufacturing-grade metrology.",
    ]

    return {
        "file_type": "image",
        "width_px": int(w),
        "height_px": int(h),
        "dominant_color": dominant,
        "bounding_box_px": bbox,
        "silhouette": {
            "aspect_ratio": round(aspect, 4),
            "rectangularity": round(float(rectangularity), 4),
        },
        "cavity_candidates": cavity_candidates,
        "feature_flags": {
            "top_dual_rails": bool(top_dual),
            "front_shroud": bool(front_shroud),
            "side_latch_like": bool(side_latch),
        },
        "warnings": warnings,
    }


def summarize_features_for_storage(features: dict[str, Any]) -> dict[str, Any]:
    """Smaller payload attached to job params for UI."""
    return {
        "dominant_color": features.get("dominant_color"),
        "bounding_box_px": features.get("bounding_box_px"),
        "silhouette": features.get("silhouette"),
        "cavity_count": len(features.get("cavity_candidates") or []),
        "feature_flags": features.get("feature_flags"),
        "warnings": features.get("warnings"),
    }
