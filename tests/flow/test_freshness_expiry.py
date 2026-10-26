import json
from datetime import datetime, timedelta, timezone

from caseproof.adapters.provider import Provider
from caseproof.domain.ledger import dt
from tests.flow.test_api import client
from tests.flow.test_bank_ingestion import batch

ADMIN = {"X-Demo-User": "admin"}
REVIEWER = {"X-Demo-User": "reviewer"}


def prepare(c, tmp_path):
    o = c.app.state.orchestrator
    o.s.llm_provider = "local"
    o.s.customer_portal = True
    o.s.trail_feed_path = tmp_path / "feed.json"
    o.llm = Provider(o.s)
    net = c.post(
        "/v1/local/bank-network", json={"network_id": "FRESHNESS", "seed": 35}, headers=ADMIN
    ).json()
    cid = c.post(
        "/v1/cases", json={k: net[k] for k in ("customer_account", "first_contact", "reported_at")}
    ).json()["case_id"]

    def submit(url, notes):
        token = url.rsplit("/", 1)[1]
        result = c.post(f"/v1/customer/{token}/complete", json={"notes": notes})
        assert result.status_code == 200, result.text

    url = c.post(f"/v1/cases/{cid}/upload-links").json()["url"]
    submit(url, net["initial_statement"])
    req = next(r for r in o.store.get(cid).requests if r.state == "proposed")
    url = c.post(f"/v1/cases/{cid}/requests/{req.request_id}/send").json()["url"]
    submit(url, net["followup_statement"])
    assert c.post("/v1/local/bank-network/FRESHNESS/reports", headers=ADMIN).status_code == 200
    snap = o.process(cid)
    assert snap.readiness.disposition == "COMPLETE_CANDIDATE", snap.readiness.model_dump()
    assert snap.trail["summary"]["recoverable"] == 5500000
    return o, cid, net, snap


def test_own_bank_coverage_expires_and_new_observation_restores_it(tmp_path):
    from caseproof.adapters.bank_ingestion import BankIngestion

    with client(tmp_path) as c:
        body = batch()
        assert c.post("/v1/bank/imports", json=body, headers=ADMIN).status_code == 200
        ingestion = BankIngestion(c.app.state.orchestrator)
        observed = dt(body["coverage"][0]["as_of"])
        args = ("NEW-C", "demo", "2026-10-15T09:00:00+05:30", body["coverage"][0]["end"])
        assert ingestion.coverage(*args, (observed + timedelta(seconds=899)).isoformat())[
            "complete"
        ]
        stale = ingestion.coverage(*args, (observed + timedelta(seconds=900)).isoformat())
        assert stale["interval_complete"] and not stale["complete"]
        assert stale["freshness"]["state"] == "stale"
        body["batch_id"] += "-REFRESH"
        body["transactions"] = []
        body["coverage"][0]["as_of"] = (observed + timedelta(seconds=900)).isoformat()
        assert c.post("/v1/bank/imports", json=body, headers=ADMIN).status_code == 200
        fresh = ingestion.coverage(*args, body["coverage"][0]["as_of"])
        assert fresh["complete"] and fresh["batch_ids"] == [body["batch_id"]]


def test_simulator_can_refresh_observations_without_rewriting_original_dataset(tmp_path):
    with client(tmp_path) as c:
        o, cid, net, snap = prepare(c, tmp_path)
        original = c.get(net["dataset_url"]).json()
        path = "/v1/local/bank-network/FRESHNESS/refresh"
        assert c.post(path).status_code == 403
        result = c.post(path, headers=ADMIN)
        assert result.status_code == 200, result.text
        assert c.get(net["dataset_url"]).json() == original
        latest = o.process(cid)
        assert latest.trail["summary"] == snap.trail["summary"]
        assert all("REFRESH" in r["update_id"] for r in latest.trail["account_observations"])


def test_stale_balances_become_unknown_then_refresh_restores_exact_amounts(tmp_path):
    with client(tmp_path) as c:
        o, cid, net, original = prepare(c, tmp_path)
        o.clock_as_of = dt(original.clock.as_of) + timedelta(minutes=16)
        expired = o.process(cid)
        assert expired.trail["summary"] == {
            "recoverable": 0,
            "unaccounted": 5500000,
            "left_system": 500000,
        }
        assert not expired.trail["bank_verification"]["complete"]
        assert "ledger_coverage" in expired.readiness.unresolved_facts
        assert not any(
            r.state == "proposed" and "ledger_coverage" in r.explanation["can_settle"]
            for r in expired.requests
        )
        assert o.store.get(cid, original.revision).digest == original.digest
        dataset = c.get(net["dataset_url"]).json()
        dataset["batch_id"] += "-REFRESH"
        dataset["transactions"] = []
        for row in dataset["coverage"]:
            row["as_of"] = o.clock_as_of.isoformat()
        assert c.post("/v1/bank/imports", json=dataset, headers=ADMIN).status_code == 200
        rows = json.loads(o.s.trail_feed_path.read_text())
        refreshed = [
            dict(
                update_id=r["update_id"] + "-REFRESH",
                account=r["account"],
                reporting_bank=r["reporting_bank"],
                reported_at=o.clock_as_of.isoformat(),
                balance_minor=r["balance_minor"],
                credit_received=[],
                onward_transfers=[],
            )
            for r in rows
        ]
        o.s.trail_feed_path.write_text(json.dumps(rows + refreshed))
        restored = o.process(cid)
        assert restored.trail["summary"] == original.trail["summary"]
        assert restored.readiness.disposition == "COMPLETE_CANDIDATE"
        assert all(
            r["freshness"]["state"] == "fresh" for r in restored.trail["account_observations"]
        )


def test_expiry_between_review_and_delivery_blocks_unsent_but_preserves_sent_retry(
    tmp_path, monkeypatch
):
    import caseproof.domain.freshness as freshness
    from caseproof.adapters.http_outbound import HTTPOutbound

    with client(tmp_path) as c:
        o, cid, net, snap = prepare(c, tmp_path)
        review = dict(
            expected_revision=snap.revision,
            digest=snap.digest,
            disposition="COMPLETE_HANDOFF",
            reason="Fresh independent bank observations",
        )
        future = dt(snap.clock.as_of) + timedelta(minutes=16)

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return future.astimezone(tz or timezone.utc)

        monkeypatch.setattr(freshness, "datetime", Later)
        rejected = c.post(f"/v1/cases/{cid}/reviews", json=review, headers=REVIEWER)
        assert rejected.status_code == 422 and "stale_bank_data" in rejected.text
        monkeypatch.setattr(freshness, "datetime", datetime)
        assert c.post(f"/v1/cases/{cid}/reviews", json=review, headers=REVIEWER).status_code == 200
        sent = []
        monkeypatch.setattr(
            HTTPOutbound,
            "send",
            lambda self, kind, payload, key: (
                sent.append(kind) or {"status": "received_by_fictional_service"}
            ),
        )
        monkeypatch.setattr(freshness, "datetime", Later)
        assert c.post(f"/v1/cases/{cid}/exports", headers=REVIEWER).status_code == 422
        assert sent == []
        monkeypatch.setattr(freshness, "datetime", datetime)
        delivered = c.post(f"/v1/cases/{cid}/exports", headers=REVIEWER)
        assert delivered.status_code == 200, delivered.text
        assert len(sent) == 2
        monkeypatch.setattr(freshness, "datetime", Later)
        retried = c.post(f"/v1/cases/{cid}/exports", headers=REVIEWER)
        assert retried.status_code == 200 and retried.json() == delivered.json()
        assert len(sent) == 2 and len(c.get(f"/v1/cases/{cid}/approvals").json()) == 1
