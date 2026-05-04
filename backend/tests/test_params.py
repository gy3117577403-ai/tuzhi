from backend.app.cad.generator import build_params
from backend.app.models import InputMode


def test_text_params_extract_pin_count_and_pitch():
    params = build_params(InputMode.text, "2x8 2.54mm rectangular connector", None)

    assert params.dimensions.pin_count == 16
    assert params.dimensions.pin_pitch == 2.54
    assert params.source == "text_heuristic"
    assert any(item.status == "待确认" for item in params.unknowns)


def test_upload_params_mark_unknowns():
    params = build_params(InputMode.drawing, None, "drawing.pdf")

    assert params.attachment_name == "drawing.pdf"
    assert params.source == "uploaded_file_unverified"
    assert params.unknowns[0].status == "待确认"
