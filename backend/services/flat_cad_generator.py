"""Generate 2D flat connector views as DXF (ezdxf) + summary SVG."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ezdxf

from services.structure_completeness_checker import check_structure_completeness

L_OUT = "OUTLINE"
L_CAV = "CAVITY"
L_TXT = "TEXT"
L_NOTE = "NOTES"
L_ARR = "ARROW"


def _setup_layers(doc: ezdxf.Drawing) -> None:
    doc.layers.add(L_OUT, color=7)
    doc.layers.add(L_CAV, color=1)
    doc.layers.add(L_TXT, color=3)
    doc.layers.add(L_NOTE, color=30)
    doc.layers.add(L_ARR, color=5)


def _rect(msp, x0: float, y0: float, x1: float, y1: float, layer: str = L_OUT) -> None:
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], dxfattribs={"layer": layer}, close=True)


def _cavity_indices(rows: int, cols: int, active: int) -> list[tuple[int, int, int]]:
    """row-major left-to-right top-to-bottom, 1-based labels."""
    out: list[tuple[int, int, int]] = []
    n = 0
    for r in range(rows):
        for c in range(cols):
            if n >= active:
                return out
            out.append((r, c, n + 1))
            n += 1
    return out


def _write_mtext(msp, x: float, y: float, text: str, h: float = 2.5, layer: str = L_TXT, w: float = 120.0) -> None:
    msp.add_mtext(
        text,
        dxfattribs={
            "layer": layer,
            "char_height": h,
            "width": w,
            "insert": (x, y),
            "style": "Standard",
        },
    )


def _draw_front_dxf(path: Path, recipe: dict[str, Any]) -> None:
    da = recipe["dimension_assumptions"]
    W, H = float(da["body_width_mm"]), float(da["body_height_mm"])
    v = recipe["views"]["front_mating_face"]
    cav = v["cavity_array"]
    rows, cols, active = int(cav["rows"]), int(cav["cols"]), int(cav["active_positions"])
    pitch_x = float(da["cavity_pitch_x_mm"])
    pitch_y = float(da["cavity_pitch_y_mm"])
    cw, ch = float(da["cavity_width_mm"]), float(da["cavity_height_mm"])

    doc = ezdxf.new("R2010", setup=True)
    _setup_layers(doc)
    msp = doc.modelspace()
    _rect(msp, -W / 2, -H / 2, W / 2, H / 2, L_OUT)
    inset = min(W, H) * 0.12
    _rect(msp, -W / 2 + inset, -H / 2 + inset, W / 2 - inset, H / 2 - inset * 0.85, L_OUT)

    cx0 = -((cols - 1) / 2) * pitch_x
    cy0 = -((rows - 1) / 2) * pitch_y
    for r, c, label in _cavity_indices(rows, cols, active):
        x = cx0 + c * pitch_x
        y = cy0 + r * pitch_y
        if cav.get("cavity_shape") == "rounded_rect":
            _rect(msp, x - cw / 2, y - ch / 2, x + cw / 2, y + ch / 2, L_CAV)
        else:
            msp.add_circle((x, y), radius=min(cw, ch) / 2, dxfattribs={"layer": L_CAV})
        msp.add_text(str(label), dxfattribs={"layer": L_TXT, "height": min(2.8, cw * 0.35), "insert": (x - 1.0, y - 1.0)})

    _write_mtext(msp, -W / 2, H / 2 + 6, v.get("title") or "FRONT / MATING", 3.2, L_TXT, 90)
    _write_mtext(msp, -W / 2, -H / 2 - 6, f"Assumed W={W} mm H={H} mm (NOT official dims)", 2.0, L_NOTE, 90)
    _write_mtext(msp, -W / 2, -H / 2 - 10, "Non-manufacturer drawing — schematic only", 2.0, L_NOTE, 100)
    doc.saveas(str(path))


def _draw_rear_dxf(path: Path, recipe: dict[str, Any]) -> None:
    da = recipe["dimension_assumptions"]
    W, H = float(da["body_width_mm"]), float(da["body_height_mm"])
    v = recipe["views"]["rear_wire_entry_face"]
    te = v["terminal_entry_array"]
    rows, cols = int(te["rows"]), int(te["cols"])
    pitch_x = float(da["cavity_pitch_x_mm"])
    pitch_y = float(da["cavity_pitch_y_mm"])
    cw, ch = float(da["cavity_width_mm"]) * 0.92, float(da["cavity_height_mm"]) * 0.9

    doc = ezdxf.new("R2010", setup=True)
    _setup_layers(doc)
    msp = doc.modelspace()
    _rect(msp, -W / 2, -H / 2, W / 2, H / 2, L_OUT)
    cx0 = -((cols - 1) / 2) * pitch_x
    cy0 = -((rows - 1) / 2) * pitch_y
    active = int(recipe["views"]["front_mating_face"]["cavity_array"]["active_positions"])
    for r, c, label in _cavity_indices(rows, cols, active):
        x = cx0 + c * pitch_x
        y = cy0 + r * pitch_y
        _rect(msp, x - cw / 2, y - ch / 2, x + cw / 2, y + ch / 2, L_CAV)
        msp.add_text(f"T{label}", dxfattribs={"layer": L_TXT, "height": 2.2, "insert": (x - 2.0, y + H * 0.38)})

    # insertion arrow hint (into page = toward front)
    ax0, ay = W * 0.18, 0.0
    msp.add_line((ax0, ay), (W * 0.42, ay), dxfattribs={"layer": L_ARR})
    msp.add_lwpolyline([(W * 0.42, ay), (W * 0.36, ay + 1.2), (W * 0.36, ay - 1.2)], close=True, dxfattribs={"layer": L_ARR})

    _write_mtext(msp, -W / 2, H / 2 + 6, v.get("title") or "REAR / WIRE ENTRY", 3.0, L_TXT, 100)
    _write_mtext(msp, -W / 2, -H / 2 - 6, "Terminal insertion face MUST be verified with datasheet.", 2.0, L_NOTE, 110)
    doc.saveas(str(path))


def _draw_top_dxf(path: Path, recipe: dict[str, Any]) -> None:
    da = recipe["dimension_assumptions"]
    D = float(da["body_depth_mm"])
    W = float(da["body_width_mm"])
    doc = ezdxf.new("R2010", setup=True)
    _setup_layers(doc)
    msp = doc.modelspace()
    _rect(msp, -D / 2, -W / 2, D / 2, W / 2, L_OUT)
    if "dual_rails" in " ".join(recipe["views"]["top_view"].get("features") or []):
        rw, rl = W * 0.14, D * 0.32
        for sx in (-D * 0.22, D * 0.22):
            _rect(msp, sx - rl / 2, -W / 2 - rw * 0.05, sx + rl / 2, -W / 2 + rw * 0.55, L_OUT)
    _write_mtext(msp, -D / 2, W / 2 + 5, "TOP (schematic)", 2.8, L_TXT, 80)
    _write_mtext(msp, D * 0.25, W * 0.35, "FRONT", 2.5, L_TXT, 30)
    _write_mtext(msp, -D * 0.42, W * 0.35, "REAR", 2.5, L_TXT, 30)
    _write_mtext(msp, -D / 2, -W / 2 - 5, f"Depth ~ {D} mm (assumed)", 2.0, L_NOTE, 80)
    doc.saveas(str(path))


def _draw_side_dxf(path: Path, recipe: dict[str, Any]) -> None:
    da = recipe["dimension_assumptions"]
    D = float(da["body_depth_mm"])
    H = float(da["body_height_mm"])
    feats = recipe["views"]["side_view"].get("features") or []
    doc = ezdxf.new("R2010", setup=True)
    _setup_layers(doc)
    msp = doc.modelspace()
    _rect(msp, -D / 2, -H / 2, D / 2, H / 2, L_OUT)
    if "side_grooves" in feats:
        for gx in (D * 0.36, -D * 0.36):
            _rect(msp, gx - D * 0.04, -H * 0.22, gx + D * 0.04, H * 0.22, L_CAV)
    if "body_steps" in feats:
        _rect(msp, -D * 0.1, -H / 2 - 1.8, D * 0.35, -H / 2, L_OUT)
    msp.add_line((0, -H / 2), (0, -H / 2 - 4), dxfattribs={"layer": L_ARR})
    _write_mtext(msp, -2, -H / 2 - 7, "wire harness", 2.0, L_NOTE, 40)
    _write_mtext(msp, -D / 2, H / 2 + 5, "SIDE (schematic)", 2.8, L_TXT, 70)
    _write_mtext(msp, D * 0.28, H * 0.42, "FRONT", 2.2, L_TXT, 28)
    doc.saveas(str(path))


def _draw_insertion_dxf(path: Path, recipe: dict[str, Any], term: dict[str, Any]) -> None:
    doc = ezdxf.new("R2010", setup=True)
    _setup_layers(doc)
    msp = doc.modelspace()
    # rear block (left), front block (right)
    _rect(msp, -55, -15, -20, 15, L_OUT)
    _rect(msp, 20, -18, 55, 18, L_OUT)
    msp.add_line((-20, 0), (20, 0), dxfattribs={"layer": L_ARR})
    msp.add_lwpolyline([(20, 0), (14, 3), (14, -3)], close=True, dxfattribs={"layer": L_ARR})
    _write_mtext(msp, -52, 22, "REAR / wire entry (assumed)", 2.4, L_TXT, 48)
    _write_mtext(msp, 22, 22, "FRONT / mating (assumed)", 2.4, L_TXT, 48)
    ins = term.get("insertion_direction") or "rear_to_front"
    conf = term.get("confidence") or "low"
    rmc = term.get("requires_manual_confirmation", True)
    _write_mtext(msp, -52, -28, f"Insertion direction: {ins} (inferred)", 2.2, L_NOTE, 90)
    _write_mtext(msp, -52, -32, f"confidence={conf} requires_manual_confirmation={rmc}", 2.0, L_NOTE, 100)
    doc.saveas(str(path))


def _write_svg(path: Path, recipe: dict[str, Any], term: dict[str, Any]) -> None:
    da = recipe["dimension_assumptions"]
    W, H, D = da["body_width_mm"], da["body_height_mm"], da["body_depth_mm"]
    cav = recipe["views"]["front_mating_face"]["cavity_array"]
    rows, cols, active = int(cav["rows"]), int(cav["cols"]), int(cav["active_positions"])
    pw = 820
    ph = 480
    sb = []
    sb.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{pw}" height="{ph}" viewBox="0 0 {pw} {ph}">')
    sb.append('<rect width="100%" height="100%" fill="#f8fafc"/>')
    sb.append(f'<text x="16" y="28" font-size="16" fill="#0f172a">Connector flat views (schematic) — W×H×D ≈ {W}×{H}×{D} mm assumed</text>')

    def box(x, y, w, h, stroke="#334155"):
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{stroke}" stroke-width="1.5"/>'

    # Front panel
    fx, fy, fw, fh = 40, 60, 180, 140
    sb.append(box(fx, fy, fw, fh))
    sb.append(f'<text x="{fx}" y="{fy - 8}" font-size="12" fill="#475569">Front / mating</text>')
    px = float(da["cavity_pitch_x_mm"])
    py = float(da["cavity_pitch_y_mm"])
    cww = float(da["cavity_width_mm"]) * 0.6
    chh = float(da["cavity_height_mm"]) * 0.6
    cx0 = fx + fw / 2 - ((cols - 1) / 2) * (px * 0.35)
    cy0 = fy + fh / 2 - ((rows - 1) / 2) * (py * 0.35)
    nlab = 0
    for r in range(rows):
        for c in range(cols):
            if nlab >= active:
                break
            cx = cx0 + c * px * 0.35
            cy = cy0 + r * py * 0.35
            sb.append(
                f'<rect x="{cx - cww/2}" y="{cy - chh/2}" width="{cww}" height="{chh}" rx="2" fill="#e2e8f0" stroke="#64748b"/>'
            )
            nlab += 1
            sb.append(f'<text x="{cx-3}" y="{cy+4}" font-size="10" fill="#0f172a">{nlab}</text>')

    # Rear
    rx, ry, rw, rh = 260, 60, 180, 140
    sb.append(box(rx, ry, rw, rh))
    sb.append(f'<text x="{rx}" y="{ry - 8}" font-size="12" fill="#475569">Rear / wire entry</text>')
    sb.append(
        f'<polygon points="{rx + rw - 40},{ry + rh/2} {rx + rw - 55},{ry + rh/2 - 8} {rx + rw - 55},{ry + rh/2 + 8}" fill="#f97316"/>'
    )

    # Top / side mini
    sb.append(box(480, 60, 160, 90))
    sb.append(f'<text x="480" y="52" font-size="12" fill="#475569">Top (depth {D})</text>')
    sb.append(box(660, 60, 120, 90))
    sb.append(f'<text x="660" y="52" font-size="12" fill="#475569">Side</text>')

    sb.append(
        f'<text x="40" y="{ph - 40}" font-size="12" fill="#b45309">'
        f'Insertion: {term.get("insertion_direction", "unknown")} — verify physically; manual confirmation required.</text>'
    )
    sb.append("</svg>")
    path.write_text("\n".join(sb), encoding="utf-8")


def generate_flat_cad_views(
    recipe_2d: dict[str, Any],
    view_classification_full: dict[str, Any],
    terminal_analysis_full: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Write DXF/SVG + sidecar JSON; return paths and completeness report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    names = {
        "connector_front_view.dxf": output_dir / "connector_front_view.dxf",
        "connector_rear_view.dxf": output_dir / "connector_rear_view.dxf",
        "connector_top_view.dxf": output_dir / "connector_top_view.dxf",
        "connector_side_view.dxf": output_dir / "connector_side_view.dxf",
        "connector_insertion_direction.dxf": output_dir / "connector_insertion_direction.dxf",
        "connector_flat_views.svg": output_dir / "connector_flat_views.svg",
        "connector_2d_recipe.json": output_dir / "connector_2d_recipe.json",
        "connector_view_classification.json": output_dir / "connector_view_classification.json",
        "terminal_insertion.json": output_dir / "terminal_insertion.json",
    }

    term_block = terminal_analysis_full.get("terminal_insertion") or {}

    _draw_front_dxf(names["connector_front_view.dxf"], recipe_2d)
    _draw_rear_dxf(names["connector_rear_view.dxf"], recipe_2d)
    _draw_top_dxf(names["connector_top_view.dxf"], recipe_2d)
    _draw_side_dxf(names["connector_side_view.dxf"], recipe_2d)
    _draw_insertion_dxf(names["connector_insertion_direction.dxf"], recipe_2d, term_block)
    _write_svg(names["connector_flat_views.svg"], recipe_2d, term_block)

    names["connector_2d_recipe.json"].write_text(json.dumps(recipe_2d, ensure_ascii=False, indent=2), encoding="utf-8")
    names["connector_view_classification.json"].write_text(
        json.dumps(view_classification_full, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    names["terminal_insertion.json"].write_text(
        json.dumps(terminal_analysis_full, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    paths = {k: v for k, v in names.items()}

    report = check_structure_completeness(recipe_2d, paths)
    rp = output_dir / "structure_completeness_report.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["structure_completeness_report.json"] = rp

    return {"paths": paths, "structure_report": report}
