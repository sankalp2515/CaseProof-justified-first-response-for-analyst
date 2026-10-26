import json
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from caseproof.adapters.provider import Provider
from tests.flow.test_api import client


def test_new_complaint_bank_match_reply_trace_immutable_approval_and_reports(tmp_path, monkeypatch):
    import mock_services.bank_mock as receiver
    from caseproof.adapters.http_outbound import HTTPOutbound

    monkeypatch.setattr(receiver, "DB", tmp_path / "simulator.sqlite")
    with TestClient(receiver.app) as destination, client(tmp_path) as c:

        def send(self, kind, payload, idempotency_key):
            response = destination.post(
                "/" + kind, json=payload, headers={"Idempotency-Key": idempotency_key}
            )
            response.raise_for_status()
            return response.json()

        monkeypatch.setattr(HTTPOutbound, "send", send)
        o = c.app.state.orchestrator
        o.s.customer_portal = True
        o.s.llm_provider = "local"
        o.s.trail_feed_path = tmp_path / "feed.json"
        o.s.trail_feed_path.write_text(
            json.dumps(
                [
                    {
                        "update_id": "UNRELATED",
                        "account": "OTHER-M",
                        "reporting_bank": "Other Demo Bank",
                        "reported_at": "2026-10-01T00:00:00+05:30",
                        "balance_minor": 10000,
                        "onward_transfers": [],
                        "credit_received": [
                            {
                                "txn_id": "OTHER-T",
                                "ts": "2026-09-30T23:00:00+05:30",
                                "from_account": "OTHER-C",
                                "to_account": "OTHER-M",
                                "amount_minor": 10000,
                                "channel": "UPI",
                                "reference": "SYNTH-TX-OTHER",
                                "source": "ledger",
                            }
                        ],
                    }
                ]
            )
        )
        o.llm = Provider(o.s)
        admin = {"X-Demo-User": "admin"}
        reviewer = {"X-Demo-User": "reviewer"}
        net = c.post(
            "/v1/local/bank-network", json={"network_id": "FRESH-E2E", "seed": 35}, headers=admin
        ).json()
        assert c.get("/v1/cases").json() == []
        cid = c.post(
            "/v1/cases",
            json={k: net[k] for k in ("customer_account", "first_contact", "reported_at")},
        ).json()["case_id"]
        assert c.get("/v1/cases/" + cid).json()["artifacts"] == []

        def submit(url, notes):
            token = urlsplit(url).path.rsplit("/", 1)[1]
            response = c.post("/v1/customer/" + token + "/complete", json={"notes": notes})
            assert response.status_code == 200, response.text
            assert c.get("/v1/jobs/" + response.json()["job_id"]).json()["status"] == "done"

        submit(c.post(f"/v1/cases/{cid}/upload-links").json()["url"], net["initial_statement"])
        snap = c.get("/v1/cases/" + cid).json()
        assert len(snap["ledger_matches"]) == 1 and len(snap["unreported"]) == 1
        assert snap["trail"]["bank_verification"]["complete"]
        assert snap["trail"]["summary"]["unaccounted"] == 6000000
        requests = [r for r in snap["requests"] if r["state"] == "proposed"]
        assert requests[0]["catalogue_id"] == "confirm_additional_transfer"
        assert not any(
            r["catalogue_id"] in ("request_reference_crop", "request_transaction_receipt")
            for r in requests
        )
        reply_url = c.post(f"/v1/cases/{cid}/requests/{requests[0]['request_id']}/send").json()[
            "url"
        ]
        submit(reply_url, net["followup_statement"])
        published = c.post("/v1/local/bank-network/FRESH-E2E/reports", headers=admin)
        assert published.status_code == 200, published.text
        snap = c.get("/v1/cases/" + cid).json()
        assert snap["readiness"]["disposition"] == "COMPLETE_CANDIDATE"
        assert len(snap["ledger_matches"]) == 2 and not snap["unreported"]
        assert snap["trail"]["summary"] == {
            "recoverable": 5500000,
            "left_system": 500000,
            "unaccounted": 0,
        }
        review = {
            "expected_revision": snap["revision"],
            "digest": snap["digest"],
            "disposition": "COMPLETE_HANDOFF",
            "reason": "Checked independent synthetic bank data and victim evidence",
        }
        a = c.post(f"/v1/cases/{cid}/reviews", json=review, headers=reviewer)
        assert a.status_code == 200, a.text
        assert (
            c.post(f"/v1/cases/{cid}/reviews", json=review, headers=reviewer).json()["approval_id"]
            == a.json()["approval_id"]
        )
        assert (
            c.post(
                f"/v1/cases/{cid}/reviews", json={**review, "reason": "Changed"}, headers=reviewer
            ).status_code
            == 409
        )
        first = c.post(f"/v1/cases/{cid}/exports", headers=reviewer)
        assert first.status_code == 200, first.text
        second = c.post(f"/v1/cases/{cid}/exports", headers=reviewer)
        assert first.json() == second.json() and len(first.json()["outbound"]) == 2
        assert len(c.get(f"/v1/cases/{cid}/approvals").json()) == 1
        original_digest = o.store.get(cid, snap["revision"]).digest
        # New bank data must invalidate an approved case before background processing finishes.
        supplement = c.get(net["dataset_url"]).json()
        supplement["batch_id"] += "-SUPPLEMENT"
        supplement["transactions"] = []
        o.s.external_worker = True
        imported = c.post("/v1/bank/imports", json=supplement, headers=admin)
        assert imported.status_code == 200 and imported.json()["reprocess_jobs"], imported.text
        assert c.post(f"/v1/cases/{cid}/exports", headers=reviewer).status_code == 409
        assert o.store.get(cid, snap["revision"]).digest == original_digest
        assert len(c.get(f"/v1/cases/{cid}/approvals").json()) == 1
