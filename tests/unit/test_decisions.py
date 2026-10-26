from caseproof.domain.contracts import CandidateClaim, CaseSnapshot, EvidenceRequest, Gap, Segment
from caseproof.domain.evidence import apply_corrections
from caseproof.domain.policy import load_policy
from caseproof.domain.readiness import assess_readiness
from caseproof.domain.requests import blocked, select_requests


def test_ledger_known_fact_request_suppressed():
    rs = select_requests(
        [Gap(gap_id="g", required_fact="transaction_reference", resolvable_by="ledger")],
        [],
        load_policy(),
    )
    assert any(r.state == "suppressed" and r.reason == "bank record has it" for r in rs)


def test_secret_request_blocked():
    for term in [
        "OTP",
        "PIN",
        "password",
        "CVV",
        "full device access",
        "full chat history",
        "unrelated ID document",
    ]:
        assert blocked("please share " + term)
    p = load_policy()
    p["catalogue"].append(
        dict(
            catalogue_id="secret",
            text="send OTP",
            facts=["amount"],
            components=dict(R=5, C=0, U=0, A=1, E=0, P=0),
        )
    )
    rs = select_requests([Gap(gap_id="g", required_fact="amount")], [], p)
    assert next(r for r in rs if r.catalogue_id == "secret").state == "blocked"


def test_satisfied_gap_no_request():
    assert select_requests([], [], load_policy()) == []


def test_unavailable_not_reasked():
    h = EvidenceRequest(
        request_id="r", catalogue_id="clarify_amount", state="unavailable", reason="Device lost"
    )
    rs = select_requests([Gap(gap_id="g", required_fact="amount")], [h], load_policy())
    assert not any(r.state == "proposed" and r.catalogue_id == h.catalogue_id for r in rs)


def test_unavailable_required_allows_only_escalate():
    s = CaseSnapshot(
        case_id="C",
        revision=1,
        gaps=[Gap(gap_id="g", required_fact="amount")],
        requests=[
            EvidenceRequest(
                request_id="r",
                catalogue_id="clarify_amount",
                resolves_gap_ids=["g"],
                state="unavailable",
                reason="Lost device",
            )
        ],
    )
    assert assess_readiness(s, load_policy()).disposition == "ESCALATE_CANDIDATE"


def test_no_request_does_not_mean_complete():
    s = CaseSnapshot(case_id="C", revision=1)
    assert assess_readiness(s, load_policy()).disposition == "REVIEW_REQUIRED"


def test_correction_survives_reextract():
    s = Segment(segment_id="s", artifact_id="a", text="INR 100")
    c = CandidateClaim(
        claim_id="c", kind="amount", normalized_value=20000, anchor_segment_ids=["s"]
    )
    out = apply_corrections(
        [c],
        [dict(claim_id="c", kind="amount", value=10000, reason="typo", anchor_segment_ids=["s"])],
        [s],
    )
    assert out[0].normalized_value == 10000
