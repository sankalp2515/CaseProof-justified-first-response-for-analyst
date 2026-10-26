from copy import deepcopy

import pytest

from caseproof.domain.contracts import Actor
from tests.flow.test_api import client


def batch():
    return dict(
        batch_id="BATCH-NEW",
        synthetic=True,
        bank="Cedar Demo Bank",
        customers=[dict(account="NEW-C", display_name="Synthetic Maya")],
        accounts=[
            dict(
                id="NEW-C",
                bank="Cedar Demo Bank",
                label="Customer",
                kind="customer",
                opening_balance=1000000,
            ),
            dict(id="NEW-M", bank="Lotus Demo Bank", label="Receiver", kind="beneficiary"),
        ],
        transactions=[
            dict(
                txn_id="NEW-T1",
                account="NEW-C",
                counterparty_account="NEW-M",
                amount_minor=500000,
                payee="new@fictional.invalid",
                ts="2026-10-15T10:00:00+05:30",
                reference="SYNTH-TX-NEW1",
                direction="debit",
                channel="UPI",
            )
        ],
        coverage=[
            dict(
                account="NEW-C",
                start="2026-10-01T00:00:00+05:30",
                end="2026-10-15T10:10:00+05:30",
                as_of="2026-10-15T10:11:00+05:30",
            )
        ],
    )


def test_admin_import_idempotent_atomic_and_tenant_scoped(tmp_path):
    from caseproof.adapters.bank_ingestion import BankIngestion
    from caseproof.api.bank_contracts import BankBatch

    with client(tmp_path) as c:
        assert c.post("/v1/bank/imports", json=batch()).status_code == 403
        result = c.post("/v1/bank/imports", json=batch(), headers={"X-Demo-User": "admin"})
        assert result.status_code == 200, result.text
        assert not result.json()["duplicate"]
        assert c.post("/v1/bank/imports", json=batch(), headers={"X-Demo-User": "admin"}).json()[
            "duplicate"
        ]
        assert c.get("/v1/bank/customers").json()[0]["account"] == "NEW-C"
        o = c.app.state.orchestrator
        ingestion = BankIngestion(o)
        assert ingestion.customers("other") == []
        with pytest.raises(PermissionError):
            ingestion.check_account("NEW-C", "other")
        changed = batch()
        changed["transactions"][0]["amount_minor"] += 1
        assert (
            c.post("/v1/bank/imports", json=changed, headers={"X-Demo-User": "admin"}).status_code
            == 409
        )
        changed["batch_id"] = "DIFFERENT-BATCH"
        changed["accounts"].append(
            dict(id="SHOULD-ROLLBACK", bank="Cedar Demo Bank", label="X", kind="layer")
        )
        assert (
            c.post("/v1/bank/imports", json=changed, headers={"X-Demo-User": "admin"}).status_code
            == 409
        )
        with ingestion.bank.connect() as db:
            assert not db.execute(
                "SELECT id FROM trail_accounts WHERE id='SHOULD-ROLLBACK'"
            ).fetchall()
        with pytest.raises(PermissionError):
            ingestion.ingest(
                BankBatch.model_validate(batch()),
                Actor(user_id="a", role="admin", tenant_id="other"),
            )
        coverage = ingestion.coverage(
            "NEW-C", "demo", "2026-10-15T09:00:00+05:30", "2026-10-15T10:10:00+05:30"
        )
        assert coverage["complete"] and coverage["batch_ids"] == ["BATCH-NEW"]
        assert not ingestion.coverage(
            "NEW-C", "demo", "2026-09-01T00:00:00+05:30", "2026-10-15T10:10:00+05:30"
        )["complete"]


@pytest.mark.parametrize(
    "change", ["negative", "naive", "bad_coverage", "unknown_account", "real_data"]
)
def test_import_rejects_invalid_records_without_writes(tmp_path, change):
    body = deepcopy(batch())
    if change == "negative":
        body["transactions"][0]["amount_minor"] = -1
    if change == "naive":
        body["transactions"][0]["ts"] = "2026-10-15T10:00:00"
    if change == "bad_coverage":
        body["coverage"][0]["end"] = "2026-09-01T00:00:00+05:30"
    if change == "unknown_account":
        body["transactions"][0]["counterparty_account"] = "MISSING"
    if change == "real_data":
        body["synthetic"] = False
    with client(tmp_path) as c:
        assert (
            c.post("/v1/bank/imports", json=body, headers={"X-Demo-User": "admin"}).status_code
            == 422
        )
        assert c.get("/v1/bank/customers").json() == []


def test_coverage_does_not_use_reports_received_after_replay_time(tmp_path):
    from caseproof.adapters.bank_ingestion import BankIngestion

    with client(tmp_path) as c:
        assert (
            c.post("/v1/bank/imports", json=batch(), headers={"X-Demo-User": "admin"}).status_code
            == 200
        )
        ingestion = BankIngestion(c.app.state.orchestrator)
        assert not ingestion.coverage(
            "NEW-C",
            "demo",
            "2026-10-15T09:00:00+05:30",
            "2026-10-15T10:10:00+05:30",
            "2026-10-15T10:10:00+05:30",
        )["complete"]


@pytest.mark.parametrize("upgrade", [False, True])
def test_later_imported_historical_debit_is_hidden_from_earlier_replay(tmp_path, upgrade):
    from caseproof.adapters.provider import Provider
    from caseproof.domain.ledger import dt

    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        o.s.llm_provider = "local"
        o.s.trail_feed_path = tmp_path / "feed.json"
        o.llm = Provider(o.s)
        earlier = batch()
        earlier["batch_id"] = "EARLY-COVERAGE"
        earlier["transactions"] = []
        assert (
            c.post("/v1/bank/imports", json=earlier, headers={"X-Demo-User": "admin"}).status_code
            == 200
        )
        late = batch()
        late["batch_id"] = "LATE-DEBIT"
        late["coverage"][0]["as_of"] = "2026-10-15T10:20:00+05:30"
        assert (
            c.post("/v1/bank/imports", json=late, headers={"X-Demo-User": "admin"}).status_code
            == 200
        )
        if upgrade:
            from caseproof.adapters.duckdb_bank import DuckDBBank

            bank = DuckDBBank(o.s.duckdb_path)
            with bank.connect() as db:
                db.execute("DROP TABLE bank_transaction_observations")
            bank.initialise()
        for instant, expected in [
            ("2026-10-15T10:11:00+05:30", 0),
            ("2026-10-15T10:21:00+05:30", 1),
        ]:
            o.clock_as_of = dt(instant)
            s = o.store.create(
                customer_account="NEW-C",
                reported_at="2026-10-15T10:10:00+05:30",
                first_contact="2026-10-15T09:00:00+05:30",
            )
            o.intake.add(
                s.case_id,
                b"I paid INR 5000 on 2026-10-15 at 10:00 to new@fictional.invalid. "
                b"The caller asked for a safe account transfer.",
                "text/plain",
                "narrative",
            )
            result = o.process(s.case_id)
            assert len(result.ledger_matches) == expected
            if not expected:
                assert result.readiness.disposition == "REVIEW_REQUIRED"
                assert not result.trail.get("positions")
