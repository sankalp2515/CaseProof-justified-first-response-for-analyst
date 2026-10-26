import pytest
from sqlalchemy import text

from caseproof.adapters.http_outbound import HTTPOutbound, export
from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.config import Settings
from caseproof.domain.contracts import Actor
from caseproof.domain.review import approve
from caseproof.pipeline.orchestrator import Orchestrator


def test_same_export_key_cannot_hide_a_changed_payload(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_provider="mock",
        llm_mode="mock",
        data_dir=tmp_path,
        object_dir=tmp_path / "objects",
        sqlite_url="sqlite:///" + str(tmp_path / "db.sqlite"),
    )
    o = Orchestrator(settings)
    snapshot = o.store.create("A")
    snapshot.readiness.disposition = "COMPLETE_CANDIDATE"
    snapshot.revision += 1
    o.store.publish(snapshot, 1)
    approve(
        o.store,
        "A",
        Actor(user_id="R", role="reviewer", tenant_id="demo"),
        snapshot.revision,
        snapshot.digest,
        "COMPLETE_HANDOFF",
        "Unit reviewer",
    )
    calls = []

    def send(self, kind, payload, key):
        calls.append(kind)
        return {"message_id": kind, "synthetic": True}

    monkeypatch.setattr(HTTPOutbound, "send", send)
    original = export(o, "A")
    assert len(calls) == 2
    assert export(o, "A") == original and len(calls) == 2
    with o.store.engine.begin() as db:
        db.execute(
            text("UPDATE outbox SET payload=:body WHERE kind=:kind"),
            {"body": '{"tampered":true}', "kind": "cfcfrms_report_update"},
        )
    with pytest.raises(ConflictError, match="payload_changed"):
        export(o, "A")
    assert len(calls) == 2
