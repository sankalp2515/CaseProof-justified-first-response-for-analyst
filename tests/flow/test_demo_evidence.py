from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from caseproof.api.app import create_app
from caseproof.domain.clock import clock_state
from tests.flow.test_victim_flow import settings


def test_marked_victims_have_independent_recent_scam_payments_and_other_customers_stay_normal(
    tmp_path,
):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.post("/v1/victim/demo-session").status_code == 200
        people = client.get("/v1/victim/demo-customers").json()["customers"]
        assert len(people) == 12
        assert len({person["display_name"] for person in people}) == 12
        victims = [person for person in people if person.get("incident")]
        assert len(victims) == 6
        networks, roots = set(), set()
        for person in victims:
            assert (
                client.post(
                    "/v1/victim/sessions", json={"customer_id": person["account"]}
                ).status_code
                == 200
            )
            me = client.get("/v1/victim/me").json()
            first = next(t for t in me["transactions"] if t["txn_id"].endswith("-T1"))
            assert first["account"] == person["account"]
            assert 0 < clock_state(first["ts"]).golden_hour_remaining <= 60
            networks.add(person["network_id"])
            roots.add(first["txn_id"])
        assert len(networks) == len(roots) == 6
        for person in (person for person in people if not person.get("incident")):
            assert (
                client.post(
                    "/v1/victim/sessions", json={"customer_id": person["account"]}
                ).status_code
                == 200
            )
            rows = client.get("/v1/victim/me").json()["transactions"]
            assert rows and all(not row["txn_id"].endswith("-T1") for row in rows)


def test_samples_are_owned_real_pngs_and_local_mode_never_claims_ai(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        people = client.get("/v1/victim/demo-customers").json()["customers"]
        client.post(
            "/v1/victim/sessions",
            json={
                "customer_id": next(person for person in people if person.get("incident"))[
                    "account"
                ]
            },
        )
        tx = next(
            t
            for t in client.get("/v1/victim/me").json()["transactions"]
            if t["txn_id"].endswith("-T1")
        )
        assert not client.get("/v1/victim/sample-evidence").json()["ai_available"]
        for kind in ("receipt", "messages", "call_log"):
            r = client.post(
                "/v1/victim/sample-evidence", json={"transaction_id": tx["txn_id"], "kind": kind}
            )
            assert r.status_code == 200
            assert r.headers["X-CaseProof-Generator"] == "bank-simulator"
            assert r.headers["Cache-Control"] == "no-store"
            Image.open(BytesIO(r.content)).verify()
        assert (
            client.post(
                "/v1/victim/sample-evidence",
                json={"transaction_id": tx["txn_id"], "kind": "messages", "ai": True},
            ).status_code
            == 503
        )
        client.post(
            "/v1/victim/sessions",
            json={
                "customer_id": next(person for person in people if not person.get("incident"))[
                    "account"
                ]
            },
        )
        assert (
            client.post(
                "/v1/victim/sample-evidence",
                json={"transaction_id": tx["txn_id"], "kind": "receipt"},
            ).status_code
            == 403
        )
        assert client.get("/v1/workspace?scope=active").json()["cases"] == []


def test_priority_is_available_before_ocr_without_granting_readiness(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        person = next(
            person
            for person in client.get("/v1/victim/demo-customers").json()["customers"]
            if person.get("incident")
        )
        client.post("/v1/victim/sessions", json={"customer_id": person["account"]})
        transactions = client.get("/v1/victim/me").json()["transactions"]
        selected = [t["txn_id"] for t in transactions if t["txn_id"].endswith(("-HISTORY", "-T1"))]
        response = client.post(
            "/v1/victim/complaints",
            json={
                "submission_id": "priority-before-ai",
                "narrative": "Please review these payments.",
                "transaction_ids": selected + selected,
                "payment_authorisation": "unsure",
            },
        )
        assert response.status_code == 200
        cid = response.json()["case_id"]
        snapshot = client.app.state.orchestrator.store.get(cid)
        assert not snapshot.segments and not snapshot.ledger_matches
        assert len(snapshot.trail["intake_debit_times"]) == len(selected)
        flow = client.get(f"/v1/cases/{cid}/workflow").json()
        assert 0 < flow["clock"]["golden_hour_remaining"] <= 60
        assert flow["confirmed_disputed_minor"] == 0
        row = client.get("/v1/workspace?scope=active").json()["cases"][0]
        assert row["selected_bank_amount_minor"] == sum(
            t["amount_minor"] for t in transactions if t["txn_id"] in selected
        )
        assert not flow["urgent_referral"]["eligible"]
        assert flow["readiness"] == "REVIEW_REQUIRED"
        receipt = client.get(f"/v1/victim/complaints/{cid}").json()
        assert receipt["artifacts"][0]["sha256"] == snapshot.artifacts[0].sha256
        assert "object_key" not in receipt["artifacts"][0]
        assert receipt["processing"]["state"] == "queued"
        assert client.get("/v1/ui-config").json()["evidence"]["max_artifacts"] == 6
