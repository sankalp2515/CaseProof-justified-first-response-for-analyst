import pytest

from caseproof.adapters.literal_extractor import LiteralExtractor
from caseproof.domain.contracts import ArtifactRef, CaseSnapshot, LedgerMatch, Segment
from caseproof.domain.policy import load_policy
from caseproof.domain.readiness import assess_readiness, needs_readable_receipt
from caseproof.domain.selected_payments import flag_conflicts
from caseproof.domain.validator import validate_claims


def fixture():
    s = CaseSnapshot(case_id="AMBIG", revision=1)
    s.artifacts = [
        ArtifactRef(
            artifact_id="A",
            case_id="AMBIG",
            kind="receipt",
            mime_type="image/png",
            sha256="a" * 64,
            byte_count=100,
            object_key="aa/" + "a" * 64,
        )
    ]
    s.segments = [
        Segment(segment_id="seg-A-0", artifact_id="A", text="INR 521 23.45", source="model_ocr"),
        Segment(segment_id="seg-A-1", artifact_id="A", text="SYNTH-TX-ONE", source="model_ocr"),
    ]
    s.claims = validate_claims(
        LiteralExtractor().extract_claims("AMBIG", 1, s.segments).claims, s.segments
    )
    s.ledger_matches = [
        LedgerMatch(
            txn_id="TX",
            claim_ids=[],
            match_fields=[],
            resolved_fields={"amount": 5212345, "transaction_reference": "SYNTH-TX-ONE"},
        )
    ]
    return s


def test_fragmented_amount_is_unknown_not_a_plausible_prefix_value():
    s = fixture()
    amounts = [c for c in s.claims if c.kind == "amount"]
    assert len(amounts) == 1
    assert amounts[0].normalized_value is None
    assert amounts[0].evidence_state == "unresolved"
    assert needs_readable_receipt(s)
    assert "readable_receipt" in assess_readiness(s, load_policy()).unresolved_facts


def test_bank_selection_cannot_promote_unknown_ocr_into_a_numeric_conflict():
    s = fixture()
    flag_conflicts(
        s,
        [
            dict(
                txn_id="TX",
                reference="SYNTH-TX-ONE",
                amount_minor=5212345,
                payee="p@fictional.invalid",
                ts="2026-10-16T12:00:00+05:30",
            )
        ],
        {"TX"},
    )
    amount = next(c for c in s.claims if c.kind == "amount")
    assert amount.evidence_state == "unresolved" and amount.normalized_value is None


@pytest.mark.parametrize("state", ["source_supported", "reported"])
def test_corroborated_replacement_resolves_readability_without_erasing_original(state):
    from caseproof.domain.contracts import CandidateClaim

    s = fixture()
    for claim in s.claims:
        if claim.evidence_state == "source_supported":
            claim.evidence_state = state
    s.artifacts.append(s.artifacts[0].model_copy(update={"artifact_id": "B"}))
    s.segments.append(
        Segment(
            segment_id="seg-B-0",
            artifact_id="B",
            text="INR 52,123.45 SYNTH-TX-ONE",
            source="model_ocr",
        )
    )
    for kind, value in [("amount", 5212345), ("transaction_reference", "SYNTH-TX-ONE")]:
        s.claims.append(
            CandidateClaim(
                claim_id="B-" + kind,
                kind=kind,
                normalized_value=value,
                anchor_segment_ids=["seg-B-0"],
                evidence_state=state,
            )
        )
    assert not needs_readable_receipt(s)
    assert next(c for c in s.claims if c.claim_id.startswith("cl-seg-A-0")).normalized_value is None
    # A different payment or amount cannot settle this original's ambiguity.
    s.claims[-1].normalized_value = "SYNTH-TX-OTHER"
    assert needs_readable_receipt(s)


def test_no_bank_oracle_can_invent_a_value_from_two_amounts_on_one_line():
    s = fixture()
    s.segments[0].text = "INR 100 200.00"
    result = LiteralExtractor().extract_claims("AMBIG", 1, s.segments)
    amount = next(c for c in result.claims if c.kind == "amount")
    assert amount.normalized_value is None


@pytest.mark.parametrize("text", ["Amount: INR 521 23.45", "Amount: 521 23.45", "Amount 521 23.45"])
def test_supported_amount_labels_cannot_bypass_the_fragment_guard(text):
    segment = Segment(segment_id="s", artifact_id="A", text=text)
    result = LiteralExtractor().extract_claims("AMBIG", 1, [segment])
    amount = next(c for c in validate_claims(result.claims, [segment]) if c.kind == "amount")
    assert amount.normalized_value is None and amount.evidence_state == "unresolved"


def blank_with_other_receipt():
    s = fixture()
    s.artifacts.append(s.artifacts[0].model_copy(update={"artifact_id": "B", "stage": "followup"}))
    s.segments = [Segment(segment_id="B0", artifact_id="B", text="INR 52,123.45 SYNTH-TX-ONE")]
    s.claims = validate_claims(
        LiteralExtractor().extract_claims(s.case_id, 1, s.segments).claims, s.segments
    )
    return s


def test_another_readable_receipt_does_not_hide_an_unreadable_original():
    assert needs_readable_receipt(blank_with_other_receipt())


def test_reference_only_receipt_is_not_a_readable_financial_receipt():
    s = fixture()
    s.segments = [s.segments[1]]
    s.claims = validate_claims(
        LiteralExtractor().extract_claims(s.case_id, 1, s.segments).claims, s.segments
    )
    s.ledger_matches = []
    assert needs_readable_receipt(s)


def test_bank_known_amount_does_not_require_a_new_receipt_for_a_unique_reference():
    s = fixture()
    s.segments = [s.segments[1]]
    s.claims = validate_claims(
        LiteralExtractor().extract_claims(s.case_id, 1, s.segments).claims, s.segments
    )
    assert not needs_readable_receipt(s)
    assert not any(c.kind == "amount" for c in s.claims)


def test_fulfilled_single_artifact_replacement_resolves_only_that_original():
    from caseproof.domain.contracts import EvidenceRequest

    s = blank_with_other_receipt()
    s.requests = [
        EvidenceRequest(
            request_id="R",
            catalogue_id="request_readable_receipt",
            state="fulfilled",
            explanation={"receipt_artifact_ids": ["A"], "replacement_artifact_ids": ["B"]},
        )
    ]
    assert not needs_readable_receipt(s)
    s.artifacts.append(s.artifacts[0].model_copy(update={"artifact_id": "C"}))
    assert needs_readable_receipt(s)


def test_one_replacement_cannot_resolve_multiple_unidentified_originals():
    from caseproof.domain.contracts import EvidenceRequest

    s = blank_with_other_receipt()
    s.artifacts.append(s.artifacts[0].model_copy(update={"artifact_id": "C"}))
    s.requests = [
        EvidenceRequest(
            request_id="R",
            catalogue_id="request_readable_receipt",
            state="fulfilled",
            explanation={"receipt_artifact_ids": ["A", "C"], "replacement_artifact_ids": ["B"]},
        )
    ]
    assert needs_readable_receipt(s)


def test_scoped_reply_cannot_replace_a_known_payment_with_another_payment():
    from caseproof.domain.contracts import EvidenceRequest

    s = blank_with_other_receipt()
    original = Segment(segment_id="Aref", artifact_id="A", text="SYNTH-TX-OTHER")
    s.segments.append(original)
    s.claims += validate_claims(
        LiteralExtractor().extract_claims(s.case_id, 1, [original]).claims, [original]
    )
    s.requests = [
        EvidenceRequest(
            request_id="R",
            catalogue_id="request_readable_receipt",
            state="fulfilled",
            explanation={"receipt_artifact_ids": ["A"], "replacement_artifact_ids": ["B"]},
        )
    ]
    assert needs_readable_receipt(s)


def test_cross_artifact_amount_claim_does_not_make_each_receipt_readable():
    from caseproof.domain.contracts import CandidateClaim

    s = blank_with_other_receipt()
    s.segments.append(Segment(segment_id="Aref", artifact_id="A", text="SYNTH-TX-ONE"))
    s.claims = [
        CandidateClaim(
            claim_id="mixed",
            kind="amount",
            normalized_value=5212345,
            anchor_segment_ids=["Aref", "B0"],
            evidence_state="source_supported",
        )
    ]
    assert needs_readable_receipt(s)


def test_invalid_quote_cannot_establish_receipt_readability():
    s = fixture()
    amount = next(c for c in s.claims if c.kind == "amount")
    amount.normalized_value = 5212345
    amount.evidence_state = "unresolved"
    amount.confidence_note = "invalid_quote"
    assert needs_readable_receipt(s)
