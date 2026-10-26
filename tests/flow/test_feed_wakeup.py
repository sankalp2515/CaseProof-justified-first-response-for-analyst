import json

import httpx

from caseproof.domain.contracts import hash_json
from local_services.worker import poll_feed
from tests.flow.test_api import client


def test_feed_wakes_only_affected_cases_once(tmp_path, monkeypatch):
    (tmp_path / "feed_cursor.json").write_text(json.dumps({"hash": hash_json([]), "ids": []}))
    row = {"update_id": "new", "account": "M1"}
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: httpx.Response(
            200, json=[row], request=httpx.Request("GET", "http://feed/v1/updates")
        ),
    )
    with client(tmp_path) as c:
        orchestrator = c.app.state.orchestrator
        orchestrator.s.trail_feed_url = "http://feed"
        for cid, account in [("A", "M1"), ("B", "M2")]:
            snap = orchestrator.store.create(cid)
            snap.revision += 1
            snap.trail = {"positions": [{"account": account}]}
            orchestrator.store.publish(snap, 1)
        poll_feed(orchestrator)
        poll_feed(orchestrator)
        assert orchestrator.store.get("A").revision == 3
        assert orchestrator.store.get("B").revision == 2
        job = orchestrator.jobs.take()
        assert (job["case_id"], job["revision"]) == ("A", 3)
        assert orchestrator.jobs.take() is None


def test_feed_for_current_user_action_precedes_older_refresh_backlog(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    (tmp_path / "feed_cursor.json").write_text(json.dumps({"hash": hash_json([]), "ids": []}))
    rows = [{"update_id": "update-" + account, "account": account} for account in ("M1", "M2")]
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: httpx.Response(
            200, json=rows, request=httpx.Request("GET", "http://feed/v1/updates")
        ),
    )
    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        o.s.trail_feed_url = "http://feed"
        for cid, account, minutes in [("A-OLD", "M1", 10), ("Z-ACTIVE", "M2", 0)]:
            s = o.store.create(cid)
            s.revision += 1
            s.trail = {"positions": [{"account": account}]}
            o.store.publish(s, 1, "victim_payment_decision")
            job = o.jobs.take()
            o.jobs.finish(job["job_id"], "done", lease_token=job["lease_token"])
            from sqlalchemy import text

            with o.store.engine.begin() as db:
                db.execute(
                    text("UPDATE audit_events SET at=:at WHERE case_id=:c"),
                    {
                        "c": cid,
                        "at": (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(),
                    },
                )
        poll_feed(o)
        first, second = o.jobs.take(), o.jobs.take()
        assert first["case_id"] == "Z-ACTIVE" and first["priority"] == 10
        assert second["case_id"] == "A-OLD" and second["priority"] == 5
