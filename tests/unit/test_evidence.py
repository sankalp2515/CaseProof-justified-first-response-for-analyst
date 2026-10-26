import pytest

from caseproof.adapters.local_storage import LocalStorage
from caseproof.domain.contracts import CandidateClaim, Segment
from caseproof.domain.validator import validate_claims


def test_file_limits(tmp_path):
    store = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        store.put(b"x" * (5 * 1024 * 1024 + 1), "text/plain")


def test_signature_mismatch_rejected(tmp_path):
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).put(b"not png", "image/png")


def test_immutable_hash_and_dedup(tmp_path):
    st = LocalStorage(tmp_path)
    a = st.put(b"hello", "text/plain")
    b = st.put(b"hello", "text/plain")
    assert a == b
    assert st.read(a[0]) == b"hello"


def test_unknown_anchor_rejected():
    c = CandidateClaim(
        claim_id="c", kind="amount", normalized_value=10000, anchor_segment_ids=["bad"]
    )
    with pytest.raises(ValueError, match="unknown_anchor"):
        validate_claims([c], [])


def test_value_not_in_segment_unresolved():
    c = CandidateClaim(
        claim_id="c",
        kind="payee_vpa",
        normalized_value="fake@fictional.invalid",
        anchor_segment_ids=["s"],
    )
    cs = validate_claims(
        [c], [Segment(segment_id="s", artifact_id="a", text="Paid shop@fictional.invalid")]
    )
    assert cs[0].evidence_state == "unresolved"


def test_minor_amount_normalisation():
    c = CandidateClaim(
        claim_id="c",
        kind="amount",
        normalized_value=4827400,
        anchor_segment_ids=["s"],
        evidence_state="source_supported",
    )
    cs = validate_claims([c], [Segment(segment_id="s", artifact_id="a", text="INR 48,274.00")])
    assert cs[0].evidence_state == "source_supported"
