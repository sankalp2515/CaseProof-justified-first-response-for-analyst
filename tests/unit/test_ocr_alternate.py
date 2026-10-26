from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image

from local_services import ocr


def pixels():
    buffer = BytesIO()
    Image.new("RGB", (30, 30), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def line(text):
    return {"text": text, "box_2d": [0, 0, 20, 300]}


def test_alternate_must_preserve_characters_and_share_the_original_deadline(monkeypatch):
    calls = []

    def recognize(data, width, height, psm, timeout):
        calls.append((psm, timeout))
        return [line("INR 521 23.45" if psm == "6" else "INR 52123.45")]

    monkeypatch.setattr(ocr, "recognize_lines", recognize)
    assert ocr.recognize(pixels()) == [line("INR 52123.45")]
    assert [c[0] for c in calls] == ["6", "11"]
    assert 0 < calls[1][1] <= calls[0][1] <= 35


@pytest.mark.parametrize(
    "alternate", [[line("INR 52123.46")], [], [line("INR 52123.45"), line("INR 52123.45")]]
)
def test_alternate_cannot_guess_changed_digits_or_merge_multiple_observations(
    monkeypatch, alternate
):
    monkeypatch.setattr(
        ocr,
        "recognize_lines",
        lambda data, width, height, psm, timeout: (
            [line("INR 521 23.45")] if psm == "6" else alternate
        ),
    )
    assert ocr.recognize(pixels()) == [line("INR 521 23.45")]


def test_secondary_engine_failure_is_explicit(monkeypatch):
    def recognize(data, width, height, psm, timeout):
        if psm == "11":
            raise HTTPException(503, "OCR engine failed")
        return [line("INR 521 23.45")]

    monkeypatch.setattr(ocr, "recognize_lines", recognize)
    with pytest.raises(HTTPException) as error:
        ocr.recognize(pixels())
    assert error.value.status_code == 503


def test_amount_alternate_from_a_different_location_cannot_resolve_ambiguity(monkeypatch):
    original = {"text": "INR 100 200.00", "box_2d": [100, 100, 150, 300]}
    alternate = {"text": "INR 100200.00", "box_2d": [800, 100, 850, 300]}
    monkeypatch.setattr(
        ocr,
        "recognize_lines",
        lambda data, width, height, psm, timeout: (
            [original.copy()] if psm == "6" else [alternate.copy()]
        ),
    )
    assert ocr.recognize(pixels()) == [original]


def test_frozen_split_amount_recovers_only_from_an_actual_second_pixel_read():
    root = Path(__file__).resolve().parents[2]
    data = (root / "eval/corpora/novel_v1/N20-0.jpg").read_bytes()
    rows = ocr.recognize(data)
    assert any("INR52123.45" == r["text"].replace(" ", "").replace(",", "") for r in rows)
