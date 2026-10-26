"""Deterministic golden-hour state, urgency, and queue ordering."""

from datetime import datetime, timezone

from caseproof.domain.contracts import ClockState
from caseproof.domain.ledger import dt


def clock_state(
    first_debit: str | None,
    as_of: datetime | None = None,
    recoverable_now: int = 0,
    replay: bool = False,
    debits: list[dict] | None = None,
) -> ClockState:
    """Keep earliest history and the next valid active debit deadline; future time is unknown."""
    as_of = as_of or datetime.now(timezone.utc)
    minutes = (as_of - dt(first_debit)).total_seconds() / 60 if first_debit else None
    if minutes is not None and minutes < 0:
        minutes = None
    remaining = max(0, 60 - minutes) if minutes is not None else None
    if debits:
        elapsed = [(as_of - dt(d["ts"])).total_seconds() / 60 for d in debits if d.get("ts")]
        valid = [m for m in elapsed if m >= 0]
        active = [60 - m for m in valid if m < 60]
        remaining = min(active) if active else 0 if valid else None
    return ClockState(
        first_debit_at=first_debit,
        as_of=as_of.isoformat(),
        minutes_since_first_debit=minutes,
        golden_hour_remaining=remaining,
        recoverable_now=recoverable_now,
        replay=replay,
    )


def urgency(clock: ClockState) -> int:
    """Inside an hour = 2, inside a day = 1, otherwise 0."""
    elapsed = clock.minutes_since_first_debit
    if clock.golden_hour_remaining is not None and clock.golden_hour_remaining > 0:
        return 2
    return 0 if elapsed is None or elapsed >= 1440 else 1


def debit_times(snapshot):
    """One clock per own-bank debit; evidence timestamps are a fallback, not extra debits."""
    rows = {
        m.txn_id: {
            "txn_id": m.txn_id,
            "ts": m.resolved_fields["txn_datetime"],
            "amount_minor": m.resolved_fields["amount"],
            "basis": "bank_match",
        }
        for m in getattr(snapshot, "ledger_matches", [])
    }
    rows.update(
        {
            u.txn_id: {
                "txn_id": u.txn_id,
                "ts": u.ts,
                "amount_minor": u.amount_minor,
                "basis": "bank_unconfirmed",
            }
            for u in getattr(snapshot, "unreported", [])
            if u.txn_id not in rows
        }
    )
    if not rows:
        if not getattr(snapshot, "segments", []):
            rows.update(
                {
                    row["txn_id"]: row
                    for row in getattr(snapshot, "trail", {}).get("intake_debit_times", [])
                }
            )
    if not rows:
        for claim in getattr(snapshot, "claims", []):
            if (
                claim.kind == "txn_datetime"
                and claim.evidence_state not in ("unresolved", "conflicted")
                and "T" in str(claim.normalized_value)
            ):
                timestamp = str(claim.normalized_value)
                rows.setdefault(
                    timestamp,
                    {
                        "txn_id": "evidence:" + claim.claim_id,
                        "ts": timestamp,
                        "basis": "customer_evidence",
                    },
                )
    return sorted(rows.values(), key=lambda d: (dt(d["ts"]), d["txn_id"]))


def current_clock(snapshot, as_of=None):
    old = snapshot.clock
    if old and old.replay:
        return old
    current = clock_state(
        old.first_debit_at if old else None,
        as_of,
        recoverable_now=old.recoverable_now if old else 0,
        debits=debit_times(snapshot),
    )
    from caseproof.domain.freshness import observation_freshness

    trail = getattr(snapshot, "trail", {})
    policy = trail.get("freshness_policy", {"max_age_seconds": 900})
    if policy:
        observations = {
            "cfcfrms_update:" + row["update_id"]: row
            for row in trail.get("account_observations", [])
        }
        current.recoverable_now = sum(
            p["amount_minor"]
            for p in trail.get("positions", [])
            if p["status"] == "recoverable"
            and observation_freshness(
                observations.get(p.get("observation_source"), {}).get("reported_at"),
                current.as_of,
                policy["max_age_seconds"],
            )["state"]
            == "fresh"
        )
    return current


def rank_queue(rows: list[dict]) -> list[dict]:
    """Ascending remaining time, descending amount and link count; ID breaks ties."""

    def key(row):
        c = row["clock"]
        left = c["golden_hour_remaining"]
        band = (
            3
            if row.get("status") == "completed"
            else 0
            if left is not None and left > 0
            else 1
            if left is None
            else 2
        )
        return (
            band,
            left if band == 0 else -float(c.get("minutes_since_first_debit") or 0),
            -c["recoverable_now"],
            -row["linked_count"],
            row["case_id"],
        )

    result = sorted(rows, key=key)
    for index, row in enumerate(result, 1):
        row["position"] = index
        left = row["clock"]["golden_hour_remaining"]
        row["priority_band"] = (
            "completed"
            if row.get("status") == "completed"
            else "active"
            if left is not None and left > 0
            else "time_unknown"
            if left is None
            else "elapsed"
        )
        row["position_reason"] = (
            row["priority_band"] + ": " + f"{row['clock']['golden_hour_remaining']}"
            " minutes remaining; INR minor units "
            f"{row['clock']['recoverable_now']}"
            " recoverable; "
            f"{row['linked_count']}"
            " linked complaints"
        )
    return result
