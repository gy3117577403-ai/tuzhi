from __future__ import annotations

from pathlib import Path

from services.cad_generator import generate_connector_cad
from services.connector_params import ConnectorCadParams


def export_job_files(params: ConnectorCadParams, output_dir: Path) -> dict[str, Path]:
    origin = params.model_origin
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
        return export_appearance_job(p, output_dir)
    return generate_connector_cad(params, output_dir)
