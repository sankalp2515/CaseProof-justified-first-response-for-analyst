from datetime import datetime, timedelta, timezone

from caseproof.domain.clock import clock_state, rank_queue, urgency
from caseproof.domain.contracts import Gap
from caseproof.domain.requests import select_requests

T = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


def test_active_deadline_precedes_expired_and_completed_cases():
    def row(cid, left, elapsed, status="needs_attention"):
        return dict(
            case_id=cid,
            linked_count=0,
            status=status,
            clock=dict(
                golden_hour_remaining=left, minutes_since_first_debit=elapsed, recoverable_now=100
            ),
        )

    rows = [
        row("expired", 0, 65),
        row("active", 5, 55),
        row("unknown", None, None),
        row("completed", 1, 59, "completed"),
        row("older", 0, 200),
    ]
    assert [r["case_id"] for r in rank_queue(rows)] == [
        "active",
        "unknown",
        "older",
        "expired",
        "completed",
    ]
    assert "active" in rank_queue(rows)[0]["position_reason"].lower()


def test_multiple_debits_keep_earliest_history_but_choose_next_active_deadline():
    debits = [
        dict(txn_id="old", ts=(T - timedelta(minutes=90)).isoformat()),
        dict(txn_id="new", ts=(T - timedelta(minutes=10)).isoformat()),
        dict(txn_id="soon", ts=(T - timedelta(minutes=55)).isoformat()),
    ]
    clock = clock_state(debits[0]["ts"], T, debits=debits)
    assert clock.minutes_since_first_debit == 90
    assert clock.golden_hour_remaining == 5 and urgency(clock) == 2
    assert (
        clock_state(debits[0]["ts"], T + timedelta(minutes=6), debits=debits).golden_hour_remaining
        == 44
    )
    assert (
        clock_state(debits[0]["ts"], T + timedelta(minutes=50), debits=debits).golden_hour_remaining
        == 0
    )


def test_future_time_does_not_fabricate_a_fresh_golden_hour():
    clock = clock_state((T + timedelta(minutes=5)).isoformat(), T)
    assert clock.golden_hour_remaining is None and urgency(clock) == 0
    assert clock_state(None, T).golden_hour_remaining is None


def test_urgency_can_change_which_permitted_request_is_selected():
    policy = {
        "catalogue": [
            dict(
                catalogue_id="slow",
                facts=["amount"],
                text="Receipt please",
                components=dict(R=4, C=0, U=0, A=0, E=0, P=0),
                urgency_weight=0,
            ),
            dict(
                catalogue_id="quick",
                facts=["amount"],
                text="Confirm amount",
                components=dict(R=3, C=0, U=0, A=0, E=0, P=0),
                urgency_weight=3,
            ),
        ]
    }
    gaps = [Gap(gap_id="g", required_fact="amount")]
    assert select_requests(gaps, [], policy, 0)[0].catalogue_id == "slow"
    assert select_requests(gaps, [], policy, 2)[0].catalogue_id == "quick"
