from urllib.parse import urlsplit

from caseproof.adapters.provider import Provider
from tests.flow.test_api import client


def test_unknown_account_can_escalate_bank_gap_without_asking_victim(tmp_path):
    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        o.s.customer_portal = True
        o.s.llm_provider = "local"
        o.s.trail_feed_path = tmp_path / "feed.json"
        o.llm = Provider(o.s)
        cid = c.post(
            "/v1/cases",
            json={
                "customer_account": "UNKNOWN",
                "first_contact": "2026-10-15T09:00:00+05:30",
                "reported_at": "2026-10-15T10:30:00+05:30",
            },
        ).json()["case_id"]
        link = c.post(f"/v1/cases/{cid}/upload-links").json()["url"]
        token = urlsplit(link).path.rsplit("/", 1)[1]
        c.post(
            f"/v1/customer/{token}/complete",
            json={
                "notes": "I paid INR 100 on 2026-10-15 at 10:00. "
                "The caller asked for a safe account transfer. Reference SYNTH-TX-MISSING."
            },
        )
        snap = c.get(f"/v1/cases/{cid}").json()
        assert snap["readiness"]["disposition"] == "REVIEW_REQUIRED"
        body = {
            "expected_revision": snap["revision"],
            "reason": "Own-bank records unavailable; bank verification required.",
        }
        assert (
            c.post(
                f"/v1/cases/{cid}/bank-verification/unavailable",
                json=body,
                headers={"X-Demo-User": "reviewer"},
            ).status_code
            == 403
        )
        result = c.post(f"/v1/cases/{cid}/bank-verification/unavailable", json=body)
        assert result.status_code == 200, result.text
        snap = result.json()
        assert snap["readiness"]["disposition"] == "ESCALATE_CANDIDATE"
        assert "bank_verified" in snap["readiness"]["unresolved_facts"]
        decision = {
            "expected_revision": snap["revision"],
            "digest": snap["digest"],
            "reason": "Escalate explicitly without bank verification",
            "disposition": "COMPLETE_HANDOFF",
        }
        assert (
            c.post(
                f"/v1/cases/{cid}/reviews", json=decision, headers={"X-Demo-User": "reviewer"}
            ).status_code
            == 422
        )
        decision["disposition"] = "ESCALATE_WITH_GAPS"
        assert (
            c.post(
                f"/v1/cases/{cid}/reviews", json=decision, headers={"X-Demo-User": "reviewer"}
            ).status_code
            == 200
        )
