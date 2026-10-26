import pytest
from fastapi.testclient import TestClient

from caseproof.adapters.sqlite_casestore import CaseStore, ConflictError
from caseproof.domain.contracts import (
    Actor,
    CandidateClaim,
    ReadinessAssessment,
    Segment,
)
from caseproof.domain.packet import build_packet
from caseproof.domain.review import approve, approved_snapshot
from mock_services.bank_mock import app


def ready(tmp_path):
    store = CaseStore("sqlite:///" + str(tmp_path / "db.sqlite"))
    s = store.create("C")
    s.revision += 1
    s.readiness = ReadinessAssessment(disposition="COMPLETE_CANDIDATE")
    s.segments = [Segment(segment_id="s", artifact_id="a", text="Paid INR 100")]
    s.claims = [
        CandidateClaim(
            claim_id="c",
            kind="amount",
            normalized_value=10000,
            anchor_segment_ids=["s"],
            evidence_state="source_supported",
        )
    ]
    store.publish(s, 1)
    return store, s


reviewer = Actor(user_id="reviewer", role="reviewer", tenant_id="demo")


def test_stale_approval_409(tmp_path):
    store, s = ready(tmp_path)
    with pytest.raises(ConflictError):
        approve(store, "C", reviewer, 1, s.digest, "COMPLETE_HANDOFF", "checked")


def test_new_evidence_invalidates_export(tmp_path):
    store, s = ready(tmp_path)
    approve(store, "C", reviewer, s.revision, s.digest, "COMPLETE_HANDOFF", "checked")
    newer = s.model_copy(deep=True)
    newer.revision += 1
    store.publish(newer, s.revision)
    with pytest.raises(ConflictError):
        approved_snapshot(store, "C")


def test_analyst_cannot_approve(tmp_path):
    store, s = ready(tmp_path)
    with pytest.raises(PermissionError):
        approve(
            store,
            "C",
            Actor(user_id="analyst", role="analyst", tenant_id="demo"),
            s.revision,
            s.digest,
            "COMPLETE_HANDOFF",
            "checked",
        )


def test_packet_every_claim_has_valid_source(tmp_path):
    store, s = ready(tmp_path)
    a = approve(store, "C", reviewer, s.revision, s.digest, "COMPLETE_HANDOFF", "checked")
    packet = build_packet(s, a)
    assert packet.claims_with_sources[0]["sources"][0]["segment_id"] == "s"
    s.claims[0].anchor_segment_ids = ["unknown"]
    with pytest.raises(ValueError):
        build_packet(s, a)


def test_outbound_idempotent(tmp_path, monkeypatch):
    import mock_services.bank_mock as service

    monkeypatch.setattr(service, "DB", tmp_path / "mock.sqlite")
    with TestClient(app) as c:
        payload = {"synthetic": True, "packet_id": "P"}
        h = {"Idempotency-Key": "test-once"}
        a = c.post("/cfcfrms_report_update", json=payload, headers=h)
        b = c.post("/cfcfrms_report_update", json=payload, headers=h)
        assert a.status_code in (200, 201)
        assert a.json() == b.json()
        assert (
            c.post(
                "/cfcfrms_report_update", json={"synthetic": True, "packet_id": "Q"}, headers=h
            ).status_code
            == 409
        )


def test_mock_outputs_labelled_synthetic(tmp_path):
    store, s = ready(tmp_path)
    a = approve(store, "C", reviewer, s.revision, s.digest, "COMPLETE_HANDOFF", "checked")
    p = build_packet(s, a)
    assert p.synthetic is True
    assert p.audit["synthetic"] is True
