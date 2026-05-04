from __future__ import annotations

import json
from pathlib import Path

from services.cad_generator import generate_connector_cad
from services.connector_params import ConnectorCadParams


def export_job_files(params: ConnectorCadParams, output_dir: Path) -> dict[str, Path]:
    return generate_connector_cad(params, output_dir)
