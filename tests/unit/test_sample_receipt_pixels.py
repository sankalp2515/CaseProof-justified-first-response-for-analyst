import shutil

import pytest

from caseproof.api.demo_evidence import SampleEvidence, render_sample
from local_services.ocr import recognize


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Linux OCR image supplies Tesseract")
@pytest.mark.parametrize("suffix", ["nwwatmcffm", "tufuksudmu", "knahwrthtd", "rrkhmscska"])
def test_cropped_sample_ist_time_and_payee_survive_real_pixel_read_without_guessing_reference(
    suffix,
):
    # Zero/O in uppercase references is genuinely ambiguous to OCR. A labelled
    # crop follows the existing bank-simulator receipt contract; matching still
    # requires both sourced payee and time, never the amount alone.
    reference = "SYNTH-TX-SIM-8FF0B71441-T1"
    tx = {
        "txn_id": "SIM-8FF0B71441-T1",
        "amount_minor": 5100000,
        "ts": "2026-10-17T14:00:00+00:00",
        "payee": f"narmada.traders.{suffix}@cedardemo",
        "reference": reference,
    }
    image, generator = render_sample(
        None,
        "test-customer",
        tx,
        SampleEvidence(
            transaction_id=tx["txn_id"],
            kind="receipt",
        ),
    )
    rows = recognize(image)
    text = "\n".join(row["text"] for row in rows)
    assert "Reference crop not included" in text
    assert reference not in text
    assert "19:30" in text and "14:00" not in text
    assert "SYNTHETIC" in text and generator == "bank-simulator"
    from caseproof.adapters.literal_extractor import LiteralExtractor
    from caseproof.domain.contracts import Segment

    claims = (
        LiteralExtractor()
        .extract_claims(
            "PIXELS",
            1,
            [
                Segment(segment_id=f"pixel-{index}", artifact_id="receipt", text=row["text"])
                for index, row in enumerate(rows)
            ],
        )
        .claims
    )
    assert any(c.kind == "payee_vpa" and c.normalized_value == tx["payee"] for c in claims), text
