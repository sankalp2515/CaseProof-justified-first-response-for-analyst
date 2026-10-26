import pytest

from caseproof.domain.contracts import CandidateClaim, Segment
from caseproof.domain.validator import validate_claims


def test_adjacent_multiline_statement_supported_without_accepting_nonadjacent_splice():
    lines = [
        Segment(segment_id=str(i), artifact_id="A", text=t)
        for i, t in enumerate(
            [
                "The caller told me to transfer",
                "money to a safe account",
                "Other unrelated sentence",
            ]
        )
    ]
    claim = CandidateClaim(
        claim_id="Q",
        kind="scam_instruction",
        normalized_value="The caller told me to transfer money to a safe account",
        anchor_segment_ids=["0", "1"],
    )
    assert validate_claims([claim], lines)[0].evidence_state != "unresolved"
    claim.normalized_value = "The caller told me to transfer Other unrelated sentence"
    claim.anchor_segment_ids = ["0", "2"]
    assert validate_claims([claim], lines)[0].evidence_state == "unresolved"


def test_unsupported_pdf_is_explicitly_rejected():
    from caseproof.adapters.object_validation import validate_evidence

    with pytest.raises(ValueError, match="unsupported_mime"):
        validate_evidence(b"%PDF-1.7", "application/pdf")


def test_readable_replacement_settles_readability_without_removing_old_original():
    from caseproof.domain.contracts import ArtifactRef, CaseSnapshot, EvidenceRequest
    from caseproof.domain.policy import load_policy
    from caseproof.domain.readiness import assess_readiness, needs_readable_receipt

    s = CaseSnapshot(case_id="REPLACEMENT", revision=1)
    s.artifacts = [
        ArtifactRef(
            artifact_id=name,
            case_id=s.case_id,
            kind="receipt",
            mime_type="image/png",
            sha256="a" * 64,
            byte_count=10,
            object_key=name,
        )
        for name in ("unreadable-original", "readable-replacement")
    ]
    assert needs_readable_receipt(s)
    assert "readable_receipt" in assess_readiness(s, load_policy()).unresolved_facts
    s.segments = [Segment(segment_id="new", artifact_id="readable-replacement", text="INR 100")]
    s.artifacts[1].stage = "followup"
    s.claims = validate_claims(
        [
            CandidateClaim(
                claim_id="replacement-amount",
                kind="amount",
                normalized_value=10000,
                anchor_segment_ids=["new"],
            )
        ],
        s.segments,
    )
    # A different readable receipt alone cannot hide the unreadable original.
    assert needs_readable_receipt(s)
    s.requests = [
        EvidenceRequest(
            request_id="replacement-request",
            catalogue_id="request_readable_receipt",
            state="fulfilled",
            explanation={
                "receipt_artifact_ids": ["unreadable-original"],
                "replacement_artifact_ids": ["readable-replacement"],
            },
        )
    ]
    assert not needs_readable_receipt(s)
    result = assess_readiness(s, load_policy())
    assert "readable_receipt" not in result.unresolved_facts
    assert result.disposition == "REVIEW_REQUIRED"  # bank facts still absent
    assert len(s.artifacts) == 2


def test_unassociated_material_receipt_cannot_become_ready_with_selected_bank_payment():
    from caseproof.domain.contracts import ArtifactRef, CaseSnapshot, LedgerMatch
    from caseproof.domain.policy import load_policy
    from caseproof.domain.readiness import assess_readiness
    from caseproof.domain.selected_payments import flag_conflicts

    s = CaseSnapshot(case_id="BLURRED-PAYEE", revision=1)
    s.artifacts = [
        ArtifactRef(
            artifact_id="A",
            case_id=s.case_id,
            kind="receipt",
            mime_type="image/png",
            sha256="a" * 64,
            byte_count=10,
            object_key="object",
        )
    ]
    s.segments = [Segment(segment_id="a", artifact_id="A", text="INR 721.00")]
    s.claims = [
        CandidateClaim(
            claim_id="amount",
            kind="amount",
            normalized_value=72100,
            anchor_segment_ids=["a"],
            evidence_state="source_supported",
        )
    ]
    s.ledger_matches = [
        LedgerMatch(
            txn_id="T",
            claim_ids=[],
            match_fields=[],
            resolved_fields={
                "amount": 64000,
                "txn_datetime": "2026-10-16T01:00:00Z",
                "transaction_reference": "R",
            },
        )
    ]
    flag_conflicts(
        s,
        [
            {
                "txn_id": "T",
                "reference": "R",
                "payee": "one@fictional.invalid",
                "ts": "2026-10-16T01:00:00Z",
                "amount_minor": 64000,
            }
        ],
        {"T"},
    )
    assert s.claims[0].evidence_state == "unresolved"
    assert "receipt_association" in assess_readiness(s, load_policy()).unresolved_facts


def test_labelled_payee_ocr_spacing_is_normalised_only_with_source_support():
    from caseproof.adapters.literal_extractor import LiteralExtractor

    seg = Segment(
        segment_id="label",
        artifact_id="image",
        source="model_ocr",
        text="To: receiver-part 9@fictional.invalid",
    )
    result = LiteralExtractor().extract_claims("SPACED", 1, [seg])
    claims = validate_claims(result.claims, [seg])
    payee = next(c for c in claims if c.kind == "payee_vpa")
    assert payee.normalized_value == "receiver-part9@fictional.invalid"
    assert payee.evidence_state == "source_supported"
