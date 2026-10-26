from caseproof.domain.contracts import Gap
from caseproof.domain.policy import load_policy
from caseproof.domain.requests import select_requests


def test_unreadable_receipt_prioritised_over_confirming_reported_time():
    gaps = [
        Gap(gap_id="g-amount", required_fact="amount"),
        Gap(gap_id="g-date", required_fact="date"),
        Gap(gap_id="g-ref", required_fact="transaction_reference"),
        Gap(gap_id="g-readable", required_fact="readable_receipt"),
    ]
    assert select_requests(gaps, [], load_policy())[0].catalogue_id == "request_readable_receipt"


def test_contradiction_score_only_for_conflicting_gap():
    missing = select_requests([Gap(gap_id="g", required_fact="date")], [], load_policy())[0]
    conflicting = select_requests(
        [Gap(gap_id="g", required_fact="date", status="conflicting")], [], load_policy()
    )[0]
    assert missing.score_components["C"] == 0
    assert conflicting.score_components["C"] > 0
