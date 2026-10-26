from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from caseproof.domain.clock import clock_state
from caseproof.domain.contracts import CaseSnapshot
from local_services.worker import poll_clocks


def test_real_clock_policy_boundary_refreshes_case_but_replay_clock_does_not():
    first = datetime.now(timezone.utc) - timedelta(minutes=61)
    snapshots = {
        id: SimpleNamespace(
            case_id=id,
            revision=7,
            clock=clock_state(first.isoformat(), first + timedelta(minutes=39), replay=replay),
        )
        for id, replay in [("live", False), ("replay", True)]
    }
    calls = []
    orchestrator = SimpleNamespace(
        store=SimpleNamespace(
            list_cases=lambda: [{"case_id": id} for id in snapshots], get=lambda id: snapshots[id]
        ),
        jobs=SimpleNamespace(enqueue=lambda id, revision: calls.append(id)),
    )
    poll_clocks(orchestrator)
    assert calls == ["live"]


def test_bank_observation_expiry_queues_once_without_waiting_for_hour_boundary():
    now = datetime.now(timezone.utc)
    snap = CaseSnapshot(
        case_id="C",
        revision=3,
        clock=clock_state((now - timedelta(minutes=30)).isoformat(), now - timedelta(minutes=10)),
        trail={
            "freshness_policy": {"max_age_seconds": 900},
            "account_observations": [
                {"update_id": "U", "reported_at": (now - timedelta(minutes=16)).isoformat()}
            ],
        },
    )
    calls = []
    o = SimpleNamespace(
        store=SimpleNamespace(list_cases=lambda: [{"case_id": "C"}], get=lambda cid: snap),
        jobs=SimpleNamespace(enqueue=lambda cid, rev: calls.append(cid)),
    )
    poll_clocks(o)
    assert calls == ["C"]
    calls.clear()
    snap.clock.as_of = now.isoformat()
    poll_clocks(o)
    assert calls == []
