import pytest
from sqlalchemy import text

from caseproof.adapters.http_outbound import export, recover_pending
from caseproof.config import Settings
from caseproof.domain.contracts import Actor
from caseproof.domain.review import approve
from tests.flow.test_api import client


def test_evidence_and_processing_intent_commit_together(tmp_path):
    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        cid = o.store.create("ATOMIC").case_id
        s = o.intake.add(cid, b"Someone scammed me.", "text/plain", "narrative")
        with o.store.engine.connect() as db:
            assert (
                db.execute(text("SELECT revision FROM jobs WHERE case_id=:c"), {"c": cid}).scalar()
                == s.revision
            )


def test_failed_send_keeps_both_intents_and_recovers_without_duplicate(tmp_path, monkeypatch):
    from caseproof.adapters.http_outbound import HTTPOutbound

    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        s = o.store.create("OUT")
        s.revision += 1
        s.readiness.disposition = "COMPLETE_CANDIDATE"
        o.store.publish(s, 1)
        approve(
            o.store,
            s.case_id,
            Actor(user_id="r", role="reviewer", tenant_id="demo"),
            s.revision,
            s.digest,
            "COMPLETE_HANDOFF",
            "Checked",
        )

        def fail(*args):
            raise ConnectionError("receiver unavailable")

        monkeypatch.setattr(HTTPOutbound, "send", fail)
        with pytest.raises(ConnectionError):
            export(o, s.case_id)
        with o.store.engine.connect() as db:
            assert (
                db.execute(text("SELECT count(*) FROM outbox WHERE status='pending'")).scalar() == 2
            )
        calls = []

        def success(self, kind, payload, key):
            calls.append(key)
            return {"message_id": key, "synthetic": True}

        monkeypatch.setattr(HTTPOutbound, "send", success)
        recover_pending(o, force=True)
        export(o, s.case_id)
        assert len(calls) == len(set(calls)) == 2


def test_production_profile_cannot_start_with_synthetic_services():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_environment="production", demo_mode=True)


def test_late_revision_cancels_pending_delivery_without_erasing_old_approval(tmp_path, monkeypatch):
    from caseproof.adapters.http_outbound import HTTPOutbound, prepare_export

    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        s = o.store.create("LATE")
        s.revision += 1
        s.readiness.disposition = "COMPLETE_CANDIDATE"
        o.store.publish(s, 1)
        approve(
            o.store,
            s.case_id,
            Actor(user_id="r", role="reviewer", tenant_id="demo"),
            s.revision,
            s.digest,
            "COMPLETE_HANDOFF",
            "Reviewed before new evidence",
        )
        prepare_export(o, s.case_id)
        o.intake.add(s.case_id, b"New contradictory evidence arrived.", "text/plain", "narrative")

        def should_not_send(*args):
            pytest.fail("obsolete approved content must not be delivered")

        monkeypatch.setattr(HTTPOutbound, "send", should_not_send)
        recover_pending(o, force=True)
        with o.store.engine.connect() as db:
            assert (
                db.execute(text("SELECT count(*) FROM outbox WHERE status='stale'")).scalar() == 2
            )
            assert db.execute(text("SELECT count(*) FROM approval_history")).scalar() == 1
