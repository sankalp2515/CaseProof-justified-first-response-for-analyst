import shutil
import time
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from local_services import ocr
from local_services.ocr import recognize


@pytest.mark.skipif(not shutil.which("tesseract"), reason="real OCR regression requires Tesseract")
def test_block_receipt_keeps_iso_separator_from_pixels():
    image = Image.new("RGB", (1800, 780), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 30)
    lines = [
        "Payment acknowledgement",
        "INR 56,000.00",
        "2026-10-16T18:31",
        "Payee: safe-sim-325eb1b81a@fictional.invalid",
        "Reference: SYNTH-TX-SIM-325EB1B81A-T1",
    ]
    for i, line in enumerate(lines):
        draw.text((45, 45 + i * 92), line, font=font, fill="black")
    data = BytesIO()
    image.save(data, format="PNG")
    result = recognize(data.getvalue())
    assert any("2026-10-16T18:31" in row["text"] for row in result)


@pytest.mark.parametrize("index,time", [(0, "18:32"), (1, "18:42")])
def test_frozen_receipt_timestamp_is_recovered_from_pixels(index, time):
    root = Path(__file__).resolve().parents[2]
    rows = recognize((root / f"eval/corpora/novel_v1/N06-{index}.png").read_bytes())
    assert any(f"2026-10-16T{time}" in row["text"] for row in rows)
    assert all(0 <= value <= 1000 for row in rows for value in row["box_2d"])


@pytest.mark.parametrize("times", [("18:32", "18:33"), ("99:32", "99:32")])
def test_timestamp_reread_rejects_disagreement_or_invalid_time(monkeypatch, times):
    calls = []

    def reread(data, width, height, psm, timeout):
        calls.append(timeout)
        value = times[0 if psm == "13" else 1]
        return [{"text": f"2026-10-16T{value}", "box_2d": [100, 100, 500, 900]}]

    monkeypatch.setattr(ocr, "recognize_lines", reread)
    row = {"text": "2026-10-16118:32", "box_2d": [100, 100, 200, 500]}
    assert ocr.reread_timestamp(Image.new("L", (600, 400), 255), row, time.monotonic()) is None
    assert 0 < calls[1] <= calls[0] <= 35


def test_repeated_low_confidence_timestamp_stays_advisory(monkeypatch):
    from types import SimpleNamespace

    from caseproof.adapters import local_llm
    from caseproof.adapters.literal_extractor import LiteralExtractor
    from caseproof.domain.contracts import CaseSnapshot
    from caseproof.domain.readiness import satisfied
    from caseproof.domain.validator import validate_claims

    row = {"text": "2026-10-16T18:32", "box_2d": [100, 100, 200, 500]}
    monkeypatch.setattr(
        ocr, "recognize_lines", lambda *args, **kwargs: [{**row, "_low_confidence": True}]
    )
    observed = ocr.reread_timestamp(Image.new("L", (600, 400), 255), row, time.monotonic())
    assert observed["uncertain_timestamp"]
    monkeypatch.setattr(
        local_llm.httpx,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"lines": [observed], "model_id": "tesseract-eng-hin-bounded-v5"},
        ),
    )
    adapter = local_llm.LocalLLM(SimpleNamespace(local_ocr_url="http://ocr:8000"))
    segments, _ = adapter.transcribe_image(
        "C", SimpleNamespace(artifact_id="A", sha256="a" * 64, mime_type="image/png"), b"pixels"
    )
    segment = segments[0]
    assert segment.ocr_model_id.endswith(":uncertain-timestamp")
    snapshot = CaseSnapshot(case_id="C", revision=1, segments=[segment])
    snapshot.claims = validate_claims(
        LiteralExtractor().extract_claims("C", 1, [segment]).claims, [segment]
    )
    assert snapshot.claims[0].evidence_state == "reported"
    assert "low confidence" in snapshot.claims[0].confidence_note
    assert "date" not in satisfied(snapshot)
    from caseproof.domain.brief import build_brief, readable_brief

    assert "low confidence" in readable_brief(build_brief(snapshot))
