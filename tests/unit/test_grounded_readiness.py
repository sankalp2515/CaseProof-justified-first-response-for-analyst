from caseproof.domain.contracts import CandidateClaim, CaseSnapshot, EvidenceRequest, Gap
from caseproof.domain.policy import load_policy
from caseproof.domain.readiness import assess_readiness, satisfied
from caseproof.domain.requests import select_requests


def test_full_receipt_does_not_imply_bank_verification_or_complete_ledger():
    s = CaseSnapshot(case_id="NO-BANK", revision=1)
    for kind, value in (
        ("amount", 10000),
        ("txn_datetime", "2026-10-15T10:00:00+05:30"),
        ("transaction_reference", "SYNTH-TX-X"),
        ("scam_instruction", "safe account"),
    ):
        s.claims.append(
            CandidateClaim(
                claim_id=kind,
                kind=kind,
                normalized_value=value,
                anchor_segment_ids=["s"],
                evidence_state="source_supported",
            )
        )
    result = assess_readiness(s, load_policy())
    assert result.disposition == "REVIEW_REQUIRED"
    assert {"bank_verified", "ledger_coverage"} <= set(result.unresolved_facts)
    assert "all_transfers_accounted" not in satisfied(s)


def test_material_additional_debit_precedes_optional_narrative_gap():
    requests = select_requests(
        [
            Gap(gap_id="debit", required_fact="all_transfers_accounted", status="unconfirmed"),
            Gap(gap_id="story", required_fact="deception_account"),
        ],
        [],
        load_policy(),
        urgency_value=2,
    )
    assert requests[0].catalogue_id == "confirm_additional_transfer"
    assert requests[0].explanation["priority_reason"] == [
        "Confirm bank-discovered debit before narrative clarification"
    ]


def test_bank_only_gap_never_becomes_a_customer_request():
    assert (
        select_requests(
            [Gap(gap_id="bank", required_fact="ledger_coverage", resolvable_by="ledger")],
            [],
            load_policy(),
        )
        == []
    )


def test_fulfilled_response_that_did_not_resolve_gap_can_be_clarified_again():
    prior = EvidenceRequest(request_id="old", catalogue_id="clarify_amount", state="fulfilled")
    result = select_requests([Gap(gap_id="amount", required_fact="amount")], [prior], load_policy())
    retry = next(r for r in result if r.state == "proposed" and r.catalogue_id == "clarify_amount")
    assert retry.request_id != prior.request_id
    assert result[0] == prior


def test_new_bank_debit_reopens_a_previously_suppressed_confirmation():
    prior = EvidenceRequest(
        request_id="REQ-confirm_additional_transfer",
        catalogue_id="confirm_additional_transfer",
        state="suppressed",
    )
    result = select_requests(
        [Gap(gap_id="new", required_fact="all_transfers_accounted")], [prior], load_policy()
    )
    active = [r for r in result if r.state == "proposed"]
    assert len(active) == 1 and active[0].request_id != prior.request_id
