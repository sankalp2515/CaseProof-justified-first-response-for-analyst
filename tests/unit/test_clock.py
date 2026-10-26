from datetime import datetime, timedelta, timezone

from caseproof.domain.clock import clock_state, rank_queue, urgency
from caseproof.domain.contracts import Gap
from caseproof.domain.policy import load_policy
from caseproof.domain.requests import select_requests

T = datetime(2026, 10, 1, 11, 29, tzinfo=timezone.utc)


def test_clock_edges():
    for minutes, u in [(0, 2), (59, 2), (60, 1), (1439, 1), (1440, 0)]:
        c = clock_state(T.isoformat(), T + timedelta(minutes=minutes))
        assert c.golden_hour_remaining == max(0, 60 - minutes)
        assert urgency(c) == u
    assert clock_state(T.isoformat(), T - timedelta(minutes=1)).minutes_since_first_debit is None


def test_queue_ties_recoverability_then_links():
    rows = [
        dict(
            case_id="A", clock=dict(golden_hour_remaining=21, recoverable_now=100), linked_count=1
        ),
        dict(case_id="B", clock=dict(golden_hour_remaining=10, recoverable_now=1), linked_count=1),
        dict(
            case_id="C", clock=dict(golden_hour_remaining=21, recoverable_now=100), linked_count=2
        ),
    ]
    assert [r["case_id"] for r in rank_queue(rows)] == ["B", "C", "A"]
    assert all(r["position_reason"] for r in rank_queue(rows))


def test_urgency_changes_score_and_reminder():
    gap = [Gap(gap_id="g", required_fact="amount")]
    policy = load_policy()
    a = select_requests(gap, [], policy, urgency_value=2)[0]
    b = select_requests(gap, [], policy, urgency_value=0)[0]
    assert a.score - b.score == 2
    assert a.reminder == "Report on 1930 / cybercrime.gov.in now; don't wait for this request"
