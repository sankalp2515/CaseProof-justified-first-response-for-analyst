from fastapi.testclient import TestClient

from caseproof.api.app import create_app
from caseproof.config import Settings


def settings(tmp_path):
    return Settings(
        _env_file=None,
        llm_provider="local",
        customer_portal=True,
        preloaded_demo=True,
        data_dir=tmp_path,
        object_dir=tmp_path / "objects",
        sqlite_url="sqlite:///" + str(tmp_path / "cases.db"),
        duckdb_path=str(tmp_path / "bank.duckdb"),
        trail_feed_path=tmp_path / "feed.json",
        external_worker=True,
    )


def test_preloaded_customers_submit_once_and_are_isolated(tmp_path):
    s = settings(tmp_path)
    with TestClient(create_app(s)) as c:
        people = c.get("/v1/victim/demo-customers").json()
        assert len(people["customers"]) == 12
        assert len(people["banks"]) == 10
        first = people["customers"][0]
        assert c.get("/v1/victim/me").status_code == 403
        assert (
            c.post("/v1/victim/sessions", json={"customer_id": first["account"]}).status_code == 200
        )
        me = c.get("/v1/victim/me").json()
        tx = me["transactions"][0]
        body = {
            "submission_id": "first-report",
            "narrative": "Someone deceived me into paying.",
            "transaction_ids": [tx["txn_id"]],
            "payment_authorisation": "deceived",
        }
        receipt = c.post("/v1/victim/complaints", json=body)
        assert receipt.status_code == 200, receipt.text
        assert c.post("/v1/victim/complaints", json=body).json() == receipt.json()
        cid = receipt.json()["case_id"]
        assert len(c.get("/v1/victim/me").json()["complaints"]) == 1
        assert (
            c.post("/v1/victim/complaints", json={**body, "tenant_id": "other"}).status_code == 422
        )
        assert (
            c.post(
                "/v1/victim/complaints", json=body, headers={"Origin": "http://attacker.invalid"}
            ).status_code
            == 403
        )
        assert c.get("/v1/victim/me").headers["cache-control"] == "no-store"
        empty = c.post(
            "/v1/victim/complaints",
            json={
                "submission_id": "unknown-payment",
                "narrative": "I cannot identify the debit yet.",
                "payment_authorisation": "unsure",
            },
        )
        assert empty.status_code == 200
        unknown = c.app.state.orchestrator.process(empty.json()["case_id"])
        assert not unknown.ledger_matches
        assert unknown.readiness.disposition != "COMPLETE_CANDIDATE"
        assert c.get(f"/v1/victim/complaints/{cid}").status_code == 200
        assert (
            c.post("/v1/victim/complaints", json={**body, "narrative": "different"}).status_code
            == 409
        )
        other = people["customers"][2]
        c.post("/v1/victim/sessions", json={"customer_id": other["account"]})
        assert c.get(f"/v1/victim/complaints/{cid}").status_code == 403
        assert c.post("/v1/victim/complaints", json=body).status_code == 422
    with TestClient(create_app(s)) as c:
        assert c.get("/v1/victim/demo-customers").json() == people


def test_selected_payment_urgent_referral_and_background_reports(tmp_path, monkeypatch):
    from caseproof.adapters.http_outbound import HTTPOutbound
    from local_services.demo_world import DemoWorld

    s = settings(tmp_path)
    with TestClient(create_app(s)) as c:
        o = c.app.state.orchestrator
        ram = c.get("/v1/victim/demo-customers").json()["customers"][0]
        c.post("/v1/victim/sessions", json={"customer_id": ram["account"]})
        txs = c.get("/v1/victim/me").json()["transactions"]
        tx = next(t for t in txs if t["txn_id"].endswith("-T1"))
        cid = c.post(
            "/v1/victim/complaints",
            json={
                "submission_id": "new",
                "narrative": "A stranger tricked me.",
                "transaction_ids": [tx["txn_id"]],
                "payment_authorisation": "deceived",
            },
        ).json()["case_id"]
        snap = o.process(cid)
        assert tx["txn_id"] in {m.txn_id for m in snap.ledger_matches}
        flow = c.get(f"/v1/cases/{cid}/workflow").json()
        assert flow["confirmed_disputed_minor"] == tx["amount_minor"]
        assert flow["additional_candidate_minor"] > 0
        assert flow["urgent_referral"]["eligible"]
        body = {
            "expected_revision": snap.revision,
            "digest": snap.digest,
            "reason": "Identified bank debit confirmed disputed by victim.",
        }
        assert c.post(f"/v1/cases/{cid}/urgent-referrals", json=body).status_code == 403
        approved = c.post(
            f"/v1/cases/{cid}/urgent-referrals", json=body, headers={"X-Demo-User": "reviewer"}
        )
        assert approved.status_code == 200, approved.text
        assert (
            c.post(
                f"/v1/cases/{cid}/urgent-referrals", json=body, headers={"X-Demo-User": "reviewer"}
            ).json()
            == approved.json()
        )
        sent = []

        def send(self, kind, payload, key):
            sent.append((kind, payload, key))
            return {
                "synthetic": True,
                "status": "received_by_fictional_service",
                "message_id": "test",
            }

        monkeypatch.setattr(HTTPOutbound, "send", send)
        endpoint = f"/v1/cases/{cid}/urgent-referrals/{approved.json()['approval_id']}/send"
        assert c.post(endpoint, headers={"X-Demo-User": "reviewer"}).status_code == 200
        assert c.post(endpoint, headers={"X-Demo-User": "reviewer"}).status_code == 200
        assert len(sent) == 1 and sent[0][0] == "urgent_referral"
        DemoWorld(o).tick()
        latest = o.process(cid)
        assert latest.trail["account_observations"]
        assert latest.digest != snap.digest
        assert c.post(endpoint, headers={"X-Demo-User": "reviewer"}).status_code == 200


def test_empty_receipt_denied_candidate_and_customer_message(tmp_path):
    s = settings(tmp_path)
    with TestClient(create_app(s)) as c:
        o = c.app.state.orchestrator
        ram = c.get("/v1/victim/demo-customers").json()["customers"][0]
        c.post("/v1/victim/sessions", json={"customer_id": ram["account"]})
        txs = c.get("/v1/victim/me").json()["transactions"]
        tx = next(t for t in txs if t["txn_id"].endswith("-T1"))
        cid = c.post(
            "/v1/victim/complaints",
            json={
                "submission_id": "no-receipt",
                "narrative": "I was tricked over the phone.",
                "transaction_ids": [tx["txn_id"]],
                "payment_authorisation": "deceived",
            },
        ).json()["case_id"]
        snap = o.process(cid)
        req = next(r for r in snap.requests if r.state == "proposed")
        assert c.post(f"/v1/cases/{cid}/requests/{req.request_id}/send").status_code == 200
        inbox = c.get(f"/v1/victim/complaints/{cid}").json()
        assert inbox["messages"][0]["reply_url"]
        extra = next(t for t in txs if t["txn_id"].endswith("-T2"))
        response = c.post(
            f"/v1/victim/complaints/{cid}/payments",
            json={"transaction_id": extra["txn_id"], "disputed": False},
        )
        assert response.status_code == 200, response.text
        snap = o.process(cid)
        assert extra["txn_id"] not in {t.txn_id for t in snap.unreported}
        assert extra["txn_id"] not in {t.txn_id for t in snap.ledger_matches}
        assert (
            c.get(f"/v1/cases/{cid}/workflow").json()["confirmed_disputed_minor"]
            == tx["amount_minor"]
        )


def test_selected_bank_payment_conflicting_receipt_blocks_actions(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        o = c.app.state.orchestrator
        p = c.get("/v1/victim/demo-customers").json()["customers"][0]
        c.post("/v1/victim/sessions", json={"customer_id": p["account"]})
        tx = next(
            t for t in c.get("/v1/victim/me").json()["transactions"] if t["txn_id"].endswith("-T1")
        )
        cid = c.post(
            "/v1/victim/complaints",
            json={
                "submission_id": "conflict",
                "narrative": "Please check this scam payment.",
                "transaction_ids": [tx["txn_id"]],
                "payment_authorisation": "deceived",
            },
        ).json()["case_id"]
        from datetime import datetime, timedelta, timezone

        local = datetime.fromisoformat(tx["ts"]).astimezone(
            timezone(timedelta(hours=5, minutes=30))
        )
        bad = f"INR 999.00 on {local:%Y-%m-%d} at {local:%H:%M} to {tx['payee']}"
        assert (
            c.post(
                f"/v1/victim/complaints/{cid}/artifacts",
                files={"file": ("bad.txt", bad.encode(), "text/plain")},
                data={"kind": "receipt"},
            ).status_code
            == 200
        )
        snap = o.process(cid)
        assert any(x.evidence_state == "conflicted" for x in snap.claims)
        assert not c.get(f"/v1/cases/{cid}/workflow").json()["urgent_referral"]["eligible"]
        assert snap.readiness.disposition != "COMPLETE_CANDIDATE"


def test_complaint_retry_recovers_interrupted_evidence_intake(tmp_path, monkeypatch):
    with TestClient(create_app(settings(tmp_path))) as c:
        o = c.app.state.orchestrator
        p = c.get("/v1/victim/demo-customers").json()["customers"][0]
        c.post("/v1/victim/sessions", json={"customer_id": p["account"]})
        body = {
            "submission_id": "interrupted",
            "narrative": "I cannot find the payment but was deceived.",
            "payment_authorisation": "unsure",
        }
        add = o.intake.add

        def broken(*args, **kwargs):
            raise OSError("synthetic storage outage")

        monkeypatch.setattr(o.intake, "add", broken)
        assert c.post("/v1/victim/complaints", json=body).status_code == 500
        monkeypatch.setattr(o.intake, "add", add)
        receipt = c.post("/v1/victim/complaints", json=body)
        assert receipt.status_code == 200, receipt.text
        snap = o.store.get(receipt.json()["case_id"])
        assert len(snap.artifacts) == 1
        assert len(c.get("/v1/victim/me").json()["complaints"]) == 1


def test_restart_preserves_selected_identity_and_denial_invalidates_approval(tmp_path, monkeypatch):
    import pytest

    from caseproof.adapters.demo_identity import USERS
    from caseproof.adapters.sqlite_casestore import ConflictError
    from caseproof.domain.referral import approve, send
    from caseproof.pipeline.orchestrator import Orchestrator

    s = settings(tmp_path)
    with TestClient(create_app(s)) as c:
        o = c.app.state.orchestrator
        p = c.get("/v1/victim/demo-customers").json()["customers"][0]
        c.post("/v1/victim/sessions", json={"customer_id": p["account"]})
        tx = next(
            t for t in c.get("/v1/victim/me").json()["transactions"] if t["txn_id"].endswith("-T1")
        )
        cid = c.post(
            "/v1/victim/complaints",
            json={
                "submission_id": "restart",
                "narrative": "I report this scam payment.",
                "transaction_ids": [tx["txn_id"]],
                "payment_authorisation": "deceived",
            },
        ).json()["case_id"]
        restarted = Orchestrator(s)
        assert restarted.store.metadata(cid)["selected_transaction_ids"] == [tx["txn_id"]]
        snap = restarted.process(cid)
        decision = approve(restarted, cid, USERS["reviewer"], snap.revision, snap.digest, "Checked")

        # Decision receipt must not rely on room for another artifact.
        def broken(*args, **kwargs):
            raise OSError("evidence unavailable")

        monkeypatch.setattr(o.intake, "add", broken)
        result = c.post(
            f"/v1/victim/complaints/{cid}/payments",
            json={"transaction_id": tx["txn_id"], "disputed": False},
        )
        assert result.status_code == 200, result.text
        with pytest.raises(ConflictError):
            send(restarted, cid, decision["approval_id"], USERS["reviewer"])
        snap = restarted.process(cid)
        assert tx["txn_id"] not in {m.txn_id for m in snap.ledger_matches}


def test_background_failure_retries_without_forging_observations(tmp_path, monkeypatch):
    import json

    from caseproof.pipeline.orchestrator import Orchestrator
    from local_services.bank_network import BankNetwork
    from local_services.demo_world import DemoWorld

    o = Orchestrator(settings(tmp_path))
    world = DemoWorld(o)
    saved = world.ensure()
    from caseproof.domain.contracts import now

    for index in (0, 2):
        o.store.create(
            "WAITING-" + str(index),
            customer_account=saved["customers"][index]["account"],
            reported_at=now(),
        )
    calls = []

    def unavailable(self, nid, actor, **kwargs):
        calls.append(nid)
        if nid == saved["networks"][0]:
            raise OSError("bank unavailable")
        return {"synthetic": True}

    monkeypatch.setattr(BankNetwork, "publish_reports", unavailable)
    world.tick()
    status = json.loads((tmp_path / "world_observations.json").read_text())
    assert status["networks"][saved["networks"][0]]["status"] == "unavailable"
    assert len(calls) == 2
    world.tick()
    assert len(calls) == 2
    assert not (tmp_path / "feed.json").exists()


def test_in_process_worker_handles_victim_submission(tmp_path):
    s = settings(tmp_path)
    s.external_worker = False
    with TestClient(create_app(s)) as c:
        p = c.get("/v1/victim/demo-customers").json()["customers"][0]
        c.post("/v1/victim/sessions", json={"customer_id": p["account"]})
        cid = c.post(
            "/v1/victim/complaints",
            json={
                "submission_id": "inline",
                "narrative": "I need help reporting this incident.",
                "payment_authorisation": "unsure",
            },
        ).json()["case_id"]
        assert c.app.state.orchestrator.store.get(cid).segments


def test_operator_fresh_session_preserves_prior_customer_and_history(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        before = c.get("/v1/victim/demo-customers").json()
        ram = before["customers"][0]
        c.post("/v1/victim/sessions", json={"customer_id": ram["account"]})
        receipt = c.post(
            "/v1/victim/complaints",
            json={
                "submission_id": "before-session",
                "narrative": "I report this incident.",
                "payment_authorisation": "unsure",
            },
        ).json()
        endpoint = "/v1/local/demo-sessions"
        body = {"session_id": "fresh-session"}
        assert c.post(endpoint, json=body).status_code == 403
        fresh = c.post(endpoint, json=body, headers={"X-Demo-User": "admin"})
        assert fresh.status_code == 200, fresh.text
        after = c.get("/v1/victim/demo-customers").json()
        assert len(after["customers"]) == 12
        assert after["customers"][0]["account"] != ram["account"]
        assert c.get("/v1/victim/me").json()["customer"]["account"] == ram["account"]
        assert c.get("/v1/victim/complaints/" + receipt["case_id"]).status_code == 200
        assert c.post(endpoint, json=body, headers={"X-Demo-User": "admin"}).json() == fresh.json()
