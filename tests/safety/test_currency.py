from caseproof.adapters.mock_llm import MockLLM
from caseproof.domain.contracts import CandidateClaim, Segment
from caseproof.domain.validator import validate_claims


def test_rupee_symbol_keeps_currency_and_amount():
    s = Segment(segment_id="s", artifact_id="a", text="I paid \u20b9100 on 2026-10-01 at 11:29")
    r = MockLLM().extract_claims("C", 1, [s])
    assert any(c.kind == "amount" and c.normalized_value == 10000 for c in r.claims)
    c = CandidateClaim(
        claim_id="c", kind="currency", normalized_value="INR", anchor_segment_ids=["s"]
    )
    assert validate_claims([c], [s])[0].evidence_state != "unresolved"
