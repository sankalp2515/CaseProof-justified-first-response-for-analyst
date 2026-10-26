import json
from types import SimpleNamespace

from local_services.worker import poll_feed
from tests.flow.test_api import client


def test_feed_invalidates_approval_revision_before_a_busy_worker_processes_it(
    tmp_path, monkeypatch
):
    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        o.s.trail_feed_url = "http://trail-feed"
        o.store.create("BACKLOG")
        o.jobs.enqueue("BACKLOG", 1)
        o.store.create("FEED-CASE")
        s = o.intake.add("FEED-CASE", b"New customer report", "text/plain", "narrative")
        old_revision = s.revision
        s.revision += 1
        s.trail = {"positions": [{"account": "RECEIVER"}]}
        s.readiness.disposition = "COMPLETE_CANDIDATE"
        o.store.publish(s, old_revision)
        cursor = tmp_path / "feed_cursor.json"
        before = {"hash": "old", "ids": []}
        cursor.write_text(json.dumps(before))
        monkeypatch.setattr(
            "local_services.worker.httpx.get",
            lambda *args, **kwargs: SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: [{"update_id": "NEW", "account": "RECEIVER"}],
            ),
        )
        poll_feed(o)
        latest = o.store.get(s.case_id)
        assert latest.revision > s.revision
        assert latest.readiness.disposition == "REVIEW_REQUIRED"
        assert latest.trail["pending_feed_update_ids"] == ["NEW"]
        # A restart between invalidation and cursor publication must not publish twice.
        cursor.write_text(json.dumps(before))
        poll_feed(o)
        assert o.store.get(s.case_id).revision == latest.revision
        assert o.jobs.take()["revision"] == latest.revision
