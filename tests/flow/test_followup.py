from tests.flow.test_api import client


def test_assignment_is_scoped_versioned_and_not_financial_approval(tmp_path):
    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        o.store.create("FOLLOWUP")
        body = {
            "expected_revision": 1,
            "expected_version": 0,
            "owner": "fraud-team-1",
            "next_action": "Check receiving bank response",
            "reason": "Assigned for follow-up",
        }
        assert (
            c.post(
                "/v1/cases/FOLLOWUP/followup", json=body, headers={"X-Demo-User": "reviewer"}
            ).status_code
            == 403
        )
        assert c.post("/v1/cases/FOLLOWUP/followup", json=body).status_code == 200
        assert c.post("/v1/cases/FOLLOWUP/followup", json=body).status_code == 409
        flow = c.get("/v1/cases/FOLLOWUP/workflow").json()
        assert flow["followup"]["owner"] == "fraud-team-1"
        assert flow["revision"] == 1 and flow["approval"] is None
        body.update(expected_version=1, due_at="2026-10-16T12:00:00")
        assert c.post("/v1/cases/FOLLOWUP/followup", json=body).status_code == 422
