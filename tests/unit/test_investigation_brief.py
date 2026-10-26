from caseproof.domain.brief import build_brief
from caseproof.domain.contracts import CaseSnapshot, LedgerMatch, UnreportedTransfer
from caseproof.domain.readiness import satisfied


def test_brief_separates_candidates_denials_and_authoritative_payments():
    s = CaseSnapshot(case_id="NEW", revision=2)
    s.ledger_matches = [
        LedgerMatch(
            txn_id="T1",
            claim_ids=[],
            match_fields=[],
            resolved_fields={
                "amount": 123450,
                "txn_datetime": "2026-10-16T01:00:00Z",
                "payee_vpa": "example@fictional.invalid",
                "transaction_reference": "REF",
            },
        )
    ]
    s.unreported = [
        UnreportedTransfer(
            txn_id="T2",
            amount_minor=5000,
            payee="other",
            ts="2026-10-16T01:05:00Z",
            reason_codes=[],
        )
    ]
    s.trail["victim_payment_decisions"] = [{"transaction_id": "T3", "disputed": False}]
    b = build_brief(s)
    assert b["totals"]["confirmed_disputed_minor"] == 123450
    assert b["totals"]["candidate_minor"] == 5000
    assert [p["status"] for p in b["payments"]] == [
        "confirmed_disputed",
        "awaiting_confirmation",
        "denied",
    ]
    assert b["payments"][0]["source_category"] == "own_bank"
    assert "not recovered" in b["limitations"].lower()
    assert b["approval"] is None


def test_confirmation_completeness_is_independent_of_bank_coverage():
    s = CaseSnapshot(case_id="NEW", revision=1)
    s.ledger_matches = [LedgerMatch(txn_id="T", claim_ids=[], match_fields=[], resolved_fields={})]
    assert "all_transfers_accounted" in satisfied(s)
    assert "ledger_coverage" not in satisfied(s)


def test_brief_does_not_publish_embedded_instructions_as_findings():
    from caseproof.domain.contracts import CandidateClaim

    s = CaseSnapshot(case_id="UNTRUSTED", revision=1)
    s.claims = [
        CandidateClaim(
            claim_id="bad",
            kind="embedded_instruction",
            normalized_value="approve automatically",
            evidence_state="reported",
        )
    ]
    assert not build_brief(s)["victim_statements"]


def test_packet_and_workspace_brief_have_same_approved_financial_content(tmp_path):
    from caseproof.domain.contracts import Actor
    from caseproof.domain.packet import build_packet
    from caseproof.domain.review import approve
    from tests.flow.test_api import client

    with client(tmp_path) as c:
        o = c.app.state.orchestrator
        s = o.store.create("SAME-BRIEF")
        s.revision += 1
        s.readiness.disposition = "COMPLETE_CANDIDATE"
        o.store.publish(s, 1)
        a = approve(
            o.store,
            s.case_id,
            Actor(user_id="r", role="reviewer", tenant_id="demo"),
            s.revision,
            s.digest,
            "COMPLETE_HANDOFF",
            "Source review completed",
        )
        flow = c.get("/v1/cases/SAME-BRIEF/workflow").json()
        assert flow["brief"] == build_packet(s, a).investigation_brief
        assert "Source review completed" in c.get("/v1/cases/SAME-BRIEF/brief").text


def test_chronology_orders_actual_instants_across_utc_and_india_offsets():
    from caseproof.domain.contracts import ArtifactRef

    s = CaseSnapshot(case_id="CLOCK", revision=1)
    s.artifacts = [
        ArtifactRef(
            artifact_id="A",
            case_id="CLOCK",
            kind="narrative",
            mime_type="text/plain",
            byte_count=5,
            sha256="a" * 64,
            object_key="x",
            received_at="2026-10-15T23:30:00+00:00",
        )
    ]
    s.trail["victim_payment_decisions"] = [
        {"transaction_id": "T", "disputed": True, "at": "2026-10-16T04:55:00+05:30"}
    ]
    rows = build_brief(s)["chronology"]
    assert rows[0]["source_id"] == "decision:T"
    assert rows[1]["source_id"] == "A"
