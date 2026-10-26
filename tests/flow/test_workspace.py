import json

from sqlalchemy import text

from caseproof.domain.contracts import Actor
from caseproof.domain.review import approve
from tests.flow.test_api import client


def test_workspace_entry_and_tenant_scope(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/", follow_redirects=False).status_code == 307
        assert c.get("/", follow_redirects=False).headers["location"] == "/inspector"
        store = c.app.state.orchestrator.store
        store.create("MINE", customer_account="A")
        store.create("OTHER", tenant_id="other", customer_account="PRIVATE")
        data = c.get("/v1/workspace").json()
        assert [r["case_id"] for r in data["cases"]] == ["MINE"]
        assert data["counts"]["total"] == 1 and data["counts"]["new"] == 1
        assert c.get("/v1/cases/OTHER/workflow").status_code == 403
        assert c.get("/v1/workspace", headers={"X-Demo-User": "intruder"}).status_code == 403


def test_workflow_only_counts_current_approval_and_both_deliveries(tmp_path):
    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        s = o.store.create("READY")
        s.revision += 1
        s.readiness.disposition = "COMPLETE_CANDIDATE"
        o.store.publish(s, 1)
        actor = Actor(user_id="r", role="reviewer", tenant_id="demo")
        a = approve(o.store, s.case_id, actor, s.revision, s.digest, "COMPLETE_HANDOFF", "Checked")
        assert c.get("/v1/cases/READY/workflow").json()["status"] == "approved"
        for i, kind in enumerate(("case_ticket", "cfcfrms_report_update")):
            with o.store.engine.begin() as db:
                db.execute(
                    text("INSERT INTO outbox VALUES(:key,'READY',2,:kind,:body,'sent',:reply)"),
                    dict(
                        key=str(i),
                        kind=kind,
                        body=json.dumps(
                            {"approval_id": a.approval_id, "packet_id": "SYNTH-PACKET-HISTORY"}
                        ),
                        reply=json.dumps({"message_id": str(i)}),
                    ),
                )
            result = c.get("/v1/cases/READY/workflow").json()
            assert result["status"] == ("approved" if i == 0 else "completed")
        assert c.get("/v1/workspace").json()["counts"]["completed"] == 1
        approve(o.store, s.case_id, actor, s.revision, s.digest, "COMPLETE_HANDOFF", "Checked")
        repeated = c.get("/v1/cases/READY/workflow").json()
        assert repeated["status"] == "completed" and len(repeated["deliveries"]) == 2
        s.revision += 1
        s.readiness.disposition = "REVIEW_REQUIRED"
        o.store.publish(s, 2)
        result = c.get("/v1/cases/READY/workflow").json()
        assert result["approval"] is None and result["deliveries"] == []
        assert result["status"] != "completed"
        assert len(result["historical_deliveries"]) == 2
        packet = c.get("/v1/cases/READY/delivered-packets/SYNTH-PACKET-HISTORY")
        assert packet.status_code == 200
        assert packet.json()["approval_id"] == a.approval_id


def test_workflow_exposes_real_job_failure_and_retry_state(tmp_path):
    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        o.store.create("JOB")
        job = o.jobs.enqueue("JOB", 1)
        assert c.get("/v1/cases/JOB/workflow").json()["status"] == "processing"
        o.jobs.finish(job, "failed", "LOCAL_OCR_ERROR")
        result = c.get("/v1/cases/JOB/workflow").json()
        assert result["status"] == "failed" and result["job"]["error"] == "LOCAL_OCR_ERROR"
        assert "lease_token" not in result["job"]
        o.jobs.retry(job)
        assert c.get("/v1/cases/JOB/workflow").json()["status"] == "processing"


def test_expired_customer_page_keeps_access_denied_and_shows_recovery_ui(tmp_path):
    with client(tmp_path) as c:
        result = c.get("/customer/" + "x" * 43)
        assert result.status_code == 403
        assert 'id="customer-form"' in result.text
        assert c.get("/v1/customer/" + "x" * 43).status_code == 403
