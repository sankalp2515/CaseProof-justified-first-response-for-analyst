import pytest
from pydantic import ValidationError

from caseproof.domain.contracts import CandidateClaim, Segment
from caseproof.domain.validator import validate_claims


@pytest.mark.parametrize("value", ["10000"])
def test_amount_must_be_integer_paisa_without_boolean_or_truncation(value):
    claim = CandidateClaim(
        claim_id="A",
        kind="amount",
        normalized_value=value,
        anchor_segment_ids=["line"],
        evidence_state="source_supported",
    )
    segment = Segment(segment_id="line", artifact_id="receipt", text="INR 100.00")
    assert validate_claims([claim], [segment])[0].evidence_state == "unresolved"


@pytest.mark.parametrize("value", [True, 10000.5])
def test_numeric_coercion_cannot_create_a_financial_claim(value):
    with pytest.raises(ValidationError):
        CandidateClaim(
            claim_id="A", kind="amount", normalized_value=value, anchor_segment_ids=["line"]
        )


def test_currency_abbreviation_is_not_a_substring_in_personal_footer():
    claim = CandidateClaim(
        claim_id="C",
        kind="currency",
        normalized_value="INR",
        anchor_segment_ids=["line"],
        evidence_state="source_supported",
    )
    segment = Segment(segment_id="line", artifact_id="receipt", text="Fictional demo / personal")
    assert validate_claims([claim], [segment])[0].evidence_state == "unresolved"
