import pytest

from caseproof.graph.engine import trace
from caseproof.graph.store import GraphStore


def test_new_bank_account_and_late_report_are_temporal_not_preseeded_answers(tmp_path):
    store = GraphStore(str(tmp_path / "bank.duckdb"))
    root = dict(
        txn_id="ROOT",
        ts="2026-10-01T11:00:00+05:30",
        from_account="V",
        to_account="M",
        amount_minor=10000,
        channel="UPI",
        reference="R",
        source="ledger",
    )
    onward = dict(
        txn_id="HOP",
        ts="2026-10-01T11:02:00+05:30",
        from_account="M",
        to_account="NEW",
        amount_minor=6000,
        channel="UPI",
        reference="H",
        source="cfcfrms_update:U1",
    )
    store.load_world(
        dict(
            accounts=[
                dict(id="V", bank="Cedar", label="V", kind="customer", opening_balance=10000),
                dict(id="M", bank="Lotus", label="M", kind="beneficiary"),
            ],
            transfers=[root, onward],
            complaint_links=[
                dict(
                    complaint_id="C",
                    victim="V",
                    txn_id="ROOT",
                    disputed_amount=10000,
                    reported_at="2026-10-01T11:01:00+05:30",
                )
            ],
            identifiers=[],
        )
    )
    assert [t.txn_id for t in store.read("2026-10-01T11:04:00+05:30")[1]] == ["ROOT"]
    row = dict(
        update_id="U1",
        account="M",
        reporting_bank="Lotus",
        reported_at="2026-10-01T11:05:00+05:30",
        credit_received=[root],
        onward_transfers=[onward],
        balance_minor=4000,
    )
    store.apply([row])
    # A subsequently stored report still must not leak into an earlier as-of investigation.
    assert [t.txn_id for t in store.read("2026-10-01T11:04:00+05:30")[1]] == ["ROOT"]
    accounts, transfers, links, _, observed = store.read("2026-10-01T11:06:00+05:30")
    result = trace(accounts, transfers, links, set(observed))
    assert {p.account: (p.amount_minor, p.status) for p in result.positions} == {
        "M": (4000, "recoverable"),
        "NEW": (6000, "unaccounted"),
    }
    store.apply(
        [
            dict(
                update_id="U2",
                account="NEW",
                reporting_bank="Tulip",
                reported_at="2026-10-01T11:08:00+05:30",
                credit_received=[onward],
                onward_transfers=[],
                balance_minor=6000,
            )
        ]
    )
    accounts, transfers, links, _, observed = store.read("2026-10-01T11:09:00+05:30")
    assert all(
        p.status == "recoverable"
        for p in trace(accounts, transfers, links, set(observed)).positions
    )
    assert next(a.bank for a in accounts if a.id == "NEW") == "Tulip"


def test_recoverable_amount_requires_current_bank_balance_source():
    from caseproof.domain.report_update import validate_trail_sources

    trail = dict(
        transfers=[dict(txn_id="ROOT", source="ledger")],
        positions=[
            dict(
                account="M",
                amount_minor=10000,
                status="recoverable",
                path=["ROOT"],
                sources=["ledger"],
            )
        ],
    )
    with pytest.raises(ValueError, match="bank observation"):
        validate_trail_sources(trail)
    trail["positions"][0]["observation_source"] = "cfcfrms_update:U1"
    trail["account_observations"] = [dict(update_id="U1", account="M", balance_minor=9000)]
    with pytest.raises(ValueError, match="exceeds"):
        validate_trail_sources(trail)
