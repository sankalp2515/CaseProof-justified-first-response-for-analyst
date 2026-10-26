from datetime import datetime, timedelta, timezone

import pytest

from caseproof.domain.contracts import CaseSnapshot
from caseproof.domain.freshness import observation_freshness, require_fresh_handoff

T = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "seconds,state", [(0, "fresh"), (899, "fresh"), (900, "stale"), (-1, "future")]
)
def test_freshness_exact_expiry_and_future(seconds, state):
    assert (
        observation_freshness((T - timedelta(seconds=seconds)).isoformat(), T, 900)["state"]
        == state
    )


def test_unknown_observation_is_not_fresh():
    assert observation_freshness(None, T, 900)["state"] == "unknown"


def test_approval_gate_checks_actual_time_without_mutating_sealed_history():
    s = CaseSnapshot(
        case_id="C",
        revision=1,
        trail={
            "freshness_policy": {"max_age_seconds": 900},
            "bank_verification": {"scope": "own_bank_debits", "observed_at": T.isoformat()},
            "positions": [{"status": "recoverable", "observation_source": "cfcfrms_update:U"}],
            "account_observations": [{"update_id": "U", "reported_at": T.isoformat()}],
        },
    ).seal()
    require_fresh_handoff(s, T + timedelta(seconds=899))
    with pytest.raises(ValueError, match="stale_bank_data"):
        require_fresh_handoff(s, T + timedelta(seconds=900))
    assert s.valid_digest()


def test_existing_snapshot_without_new_policy_metadata_cannot_claim_stale_live_availability():
    from caseproof.domain.clock import clock_state, current_clock

    s = CaseSnapshot(
        case_id="OLD",
        revision=1,
        clock=clock_state(T.isoformat(), T, recoverable_now=100),
        trail={
            "positions": [
                {
                    "status": "recoverable",
                    "amount_minor": 100,
                    "observation_source": "cfcfrms_update:U",
                }
            ],
            "account_observations": [{"update_id": "U", "reported_at": T.isoformat()}],
        },
    ).seal()
    assert current_clock(s, T + timedelta(minutes=16)).recoverable_now == 0
    with pytest.raises(ValueError, match="stale_bank_data"):
        require_fresh_handoff(s, T + timedelta(minutes=16))
    assert s.valid_digest()
