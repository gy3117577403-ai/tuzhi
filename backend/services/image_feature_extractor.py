from __future__ import annotations

import hashlib
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


def _dominant_color_robust(img_bgr: np.ndarray) -> tuple[str, float]:
    """
    Combine global mean + HSV blue-mask vote so TE-style blue housings read as blue,
    not grey noise from background / reflections.
    """
    h, w = img_bgr.shape[:2]
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    # Blue in OpenCV HSV: hue ~100-130 (two wraps handled by single range for typical connector blues)
    mask_blue = cv2.inRange(hsv, np.array([95, 35, 35]), np.array([135, 255, 255]))
    frac_blue = float(np.count_nonzero(mask_blue)) / max(h * w, 1)
    mask_dark = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([179, 255, 82]))
    frac_dark = float(np.count_nonzero(mask_dark)) / max(h * w, 1)

    mean_bgr = np.mean(img_bgr.reshape(-1, 3), axis=0)
    mean_name = _nearest_color_name(mean_bgr)

    if frac_blue >= 0.08:
        return "blue", frac_blue
    if frac_blue >= 0.04 and mean_name in ("grey", "white", "black"):
        # tinted photo — still likely blue housing if mask hits connectors
        return "blue", frac_blue
    if frac_dark >= 0.08 and frac_blue < 0.04:
        return "black", frac_blue
    return mean_name, frac_blue


def _largest_mask_bbox(mask: np.ndarray) -> dict[str, int]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"x": 0, "y": 0, "w": mask.shape[1], "h": mask.shape[0]}
    c = max(contours, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(c)
    return {"x": int(x), "y": int(y), "w": int(bw), "h": int(bh)}


def _infer_grid_from_circles(cavity_candidates: list[dict[str, Any]]) -> tuple[int, int, int, str]:
    n = len(cavity_candidates)
    if n <= 0:
        return 1, 1, 1, "low"
    if n == 1:
        return 1, 1, 1, "low"
    if n == 2:
        return 1, 2, 2, "medium"
    if n <= 4:
        return 2, 2, min(n, 4), "medium"
    rows, cols = 2, 3
    active = min(n, rows * cols)
    return rows, cols, active, "medium"


def extract_image_features(image_path: str | Path) -> dict[str, Any]:
    path = Path(image_path)
    img_bgr = cv2.imread(str(path))
    if img_bgr is None:
        pil = Image.open(path).convert("RGB")
        img_rgb = np.array(pil)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)

    dominant, blue_frac = _dominant_color_robust(img_bgr)

    # Subject silhouette: prefer blue mask contour if substantial, else largest edge contour
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask_blue = cv2.inRange(hsv, np.array([95, 35, 35]), np.array([135, 255, 255]))
    mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    if blue_frac >= 0.06:
        bbox = _largest_mask_bbox(mask_blue)
    else:
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        bbox = {"x": 0, "y": 0, "w": w, "h": h}
        if contours:
            c = max(contours, key=cv2.contourArea)
            x, y, bw, bh = cv2.boundingRect(c)
            bbox = {"x": int(x), "y": int(y), "w": int(bw), "h": int(bh)}

    aspect = float(bbox["w"]) / max(float(bbox["h"]), 1.0)
    bbox_area_ratio = (bbox["w"] * bbox["h"]) / max(w * h, 1)
    contours_main, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnt_area = 0.0
    if contours_main:
        c = max(contours_main, key=cv2.contourArea)
        cnt_area = float(cv2.contourArea(c))
    rectangularity = min(1.0, (4 * cnt_area) / max((w * h), 1.0) * 0.45 + 0.25)

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.15,
        minDist=int(min(w, h) * 0.05),
        param1=48,
        param2=22,
        minRadius=max(2, int(min(w, h) * 0.012)),
        maxRadius=int(min(w, h) * 0.24),
    )
    cavity_candidates: list[dict[str, Any]] = []
    if circles is not None:
        for cx, cy, r in np.round(circles[0]).astype(int):
            cavity_candidates.append({"cx": int(cx), "cy": int(cy), "radius_px": int(r)})
    circle_area_ratio = 0.0
    large_circle_count = 0
    for circ in cavity_candidates:
        rr = float(circ.get("radius_px") or 0)
        circle_area_ratio = max(circle_area_ratio, float(np.pi * rr * rr) / max(w * h, 1))
        if rr >= min(w, h) * 0.13:
            large_circle_count += 1

    edge_mean = float(np.mean(edges)) + 1e-6
    top_band = float(np.mean(edges[: max(1, int(h * 0.26)), :]))
    bottom_band = float(np.mean(edges[int(h * 0.68) :, :]))
    side_l = float(np.mean(edges[:, : max(1, int(w * 0.18))]))
    side_r = float(np.mean(edges[:, int(w * 0.82) :]))
    mid_y0, mid_y1 = int(h * 0.30), int(h * 0.75)
    front_band = float(np.mean(edges[mid_y0:mid_y1, :]))

    # Horizontal lines in top band → dual rails (connector crowns)
    top_roi = edges[: max(1, int(h * 0.28)), :]
    lines_top = cv2.HoughLinesP(
        top_roi, 1, np.pi / 180, threshold=max(30, int(w * 0.04)), minLineLength=int(w * 0.12), maxLineGap=12
    )
    horiz_top_count = 0
    if lines_top is not None:
        for ln in lines_top[:80]:
            x1, y1, x2, y2 = ln[0]
            ang = abs(np.arctan2(y2 - y1, x2 - x1))
            if ang < 0.35 or ang > np.pi - 0.35:
                horiz_top_count += 1

    top_dual = (top_band > edge_mean * 0.88 and top_band > 8.0) or horiz_top_count >= 2
    front_shroud = front_band > edge_mean * 0.82 or bottom_band > edge_mean * 0.88
    side_latch = side_l > 12.0 or side_r > 12.0
    wire_exit = bottom_band > edge_mean * 0.92
    round_connector = (
        (dominant != "blue" and large_circle_count >= 1)
        or (dominant != "blue" and circle_area_ratio > 0.08 and 0.45 <= aspect <= 2.0)
        or (dominant == "black" and 0.55 <= aspect <= 2.25 and rectangularity < 0.58 and bbox_area_ratio > 0.06)
    )

    # Multi cavity: circles OR busy front texture OR blue housing with structured front
    texture_front = float(np.std(blurred[mid_y0:mid_y1, :]))
    multi_cavity = (
        len(cavity_candidates) >= 2
        or front_band > edge_mean * 1.02
        or (blue_frac >= 0.06 and texture_front > 14.0)
        or (dominant == "blue" and front_band > edge_mean * 0.95)
    )
    if round_connector and len(cavity_candidates) <= 1:
        multi_cavity = False

    cx_t = (bbox["x"] + bbox["w"] / 2) / max(w, 1)
    cy_t = (bbox["y"] + bbox["h"] / 2) / max(h, 1)
    front_face_visible = (0.15 < cx_t < 0.85 and 0.10 < cy_t < 0.90 and bbox_area_ratio > 0.06) or bbox_area_ratio > 0.12

    rows_g, cols_g, active_g, layout_conf = _infer_grid_from_circles(cavity_candidates)
    if multi_cavity and len(cavity_candidates) < 2:
        rows_g, cols_g, active_g, layout_conf = 2, 3, 4, "medium"

    front_face_layout = {
        "grid_rows": rows_g,
        "grid_cols": cols_g,
        "active_positions": active_g,
        "confidence": layout_conf,
    }

    body_shape = "rectangular_housing"
    if round_connector:
        body_shape = "cylindrical_connector"
    elif rectangularity < 0.38 or bbox_area_ratio > 0.35:
        body_shape = "rounded_rectangular"

    if top_dual and aspect > 1.05:
        view_angle = "top-front"
    elif side_latch and aspect < 0.92:
        view_angle = "side-front"
    else:
        view_angle = "front"

    feat_conf = "medium"
    if bbox_area_ratio > 0.04 and (dominant == "blue" or multi_cavity or top_dual):
        feat_conf = "medium"
    if bbox_area_ratio < 0.03 and rectangularity < 0.15 and len(cavity_candidates) == 0:
        feat_conf = "low"

    warnings = [
        "Image-derived geometry is approximate and requires manual dimensional confirmation.",
        "Do not use as manufacturing-grade metrology.",
    ]

    ff = {
        "top_dual_rails": bool(top_dual),
        "top_rails": bool(top_dual),
        "front_shroud": bool(front_shroud),
        "side_latch_like": bool(side_latch),
        "side_latches": bool(side_latch),
        "side_latches_possible": bool(side_latch or (side_l > 10 or side_r > 10)),
        "multi_cavity": bool(multi_cavity),
        "wire_exit_rear": bool(wire_exit),
    }

    return {
        "file_type": "image",
        "width_px": int(w),
        "height_px": int(h),
        "dominant_color": dominant,
        "source_image_sha256": _sha256(path),
        "blue_fraction_estimate": round(blue_frac, 4),
        "body_shape": body_shape,
        "front_face_visible": bool(front_face_visible),
        "front_face_likely": bool(front_face_visible),
        "bounding_box_px": bbox,
        "silhouette": {
            "aspect_ratio": round(aspect, 4),
            "rectangularity": round(float(rectangularity), 4),
        },
        "cavity_candidates": cavity_candidates,
        "front_face_layout": front_face_layout,
        "feature_flags": ff,
        "view_angle": view_angle,
        "confidence": feat_conf,
        "warnings": warnings,
    }


def summarize_features_for_storage(features: dict[str, Any]) -> dict[str, Any]:
    """Smaller payload attached to job params for UI."""
    return {
        "dominant_color": features.get("dominant_color"),
        "source_image_sha256": features.get("source_image_sha256"),
        "body_shape": features.get("body_shape"),
        "front_face_visible": features.get("front_face_visible"),
        "bounding_box_px": features.get("bounding_box_px"),
        "silhouette": features.get("silhouette"),
        "cavity_count": len(features.get("cavity_candidates") or []),
        "front_face_layout": features.get("front_face_layout"),
        "feature_flags": features.get("feature_flags"),
        "view_angle": features.get("view_angle"),
        "confidence": features.get("confidence"),
        "warnings": features.get("warnings"),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
