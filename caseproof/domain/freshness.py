"""Explicit synthetic bank-data expiry; immutable debit facts do not expire."""

from datetime import datetime, timezone

from caseproof.domain.ledger import dt


def observation_freshness(observed_at, as_of, max_age_seconds):
    as_of = dt(as_of) if isinstance(as_of, str) else as_of
    if not observed_at:
        return {"state": "unknown", "age_seconds": None}
    age = (as_of - dt(observed_at)).total_seconds()
    return {
        "state": "future" if age < 0 else "stale" if age >= max_age_seconds else "fresh",
        "age_seconds": age,
    }


def freshness_states(snapshot, as_of):
    trail = getattr(snapshot, "trail", {})
    policy = trail.get("freshness_policy", {"max_age_seconds": 900})
    age = policy["max_age_seconds"]
    records = trail.get("account_observations", [])
    times = [r.get("reported_at") for r in records]
    bank = trail.get("bank_verification", {})
    if bank.get("scope") == "own_bank_debits":
        times.append(bank.get("observed_at"))
    return [observation_freshness(t, as_of, age)["state"] for t in times]


def require_fresh_handoff(snapshot, as_of=None, require_coverage=True):
    policy = snapshot.trail.get("freshness_policy", {"max_age_seconds": 900})
    as_of = (
        dt(snapshot.clock.as_of)
        if snapshot.clock and snapshot.clock.replay
        else as_of or datetime.now(timezone.utc)
    )
    age = policy["max_age_seconds"]
    bank = snapshot.trail.get("bank_verification", {})
    if (
        require_coverage
        and bank.get("scope") == "own_bank_debits"
        and observation_freshness(bank.get("observed_at"), as_of, age)["state"] != "fresh"
    ):
        raise ValueError("stale_bank_data: refresh own-bank coverage and reprocess")
    observations = {
        "cfcfrms_update:" + r["update_id"]: r
        for r in snapshot.trail.get("account_observations", [])
    }
    for position in snapshot.trail.get("positions", []):
        if position["status"] == "recoverable":
            row = observations.get(position.get("observation_source"), {})
            if observation_freshness(row.get("reported_at"), as_of, age)["state"] != "fresh":
                raise ValueError("stale_bank_data: refresh downstream report and reprocess")
