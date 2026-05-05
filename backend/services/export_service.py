from __future__ import annotations

from pathlib import Path

from services.cad_generator import generate_connector_cad
from services.connector_params import ConnectorCadParams


def export_job_files(params: ConnectorCadParams, output_dir: Path) -> tuple[dict[str, Path], ConnectorCadParams]:
    origin = params.model_origin
    if origin in ("image_search_approximated", "image_upload_approximated"):
        from services.visual_cad_generator import export_visual_proxy_job

        return export_visual_proxy_job(params, output_dir)
    if origin in ("series_template", "image_approximated", "generic_mvp", "parametric_mvp"):
        from services.appearance_cad_generator import export_appearance_job

        p = params
        if origin == "parametric_mvp":
            p = params.model_copy(
                update={
                    "model_origin": "generic_mvp",
                    "template_name": params.template_name or "GENERIC_RECTANGULAR_CONNECTOR",
                }
            )
        files = export_appearance_job(p, output_dir)
        return files, params
    files = generate_connector_cad(params, output_dir)
    return files, params
