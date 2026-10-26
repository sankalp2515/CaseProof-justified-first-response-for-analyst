from caseproof.domain.contracts import (
    Actor,
    Approval,
    ArtifactRef,
    CandidateClaim,
    CaseSnapshot,
    Segment,
)
from caseproof.domain.report_update import build_report_update, receipt_debits


def test_receipt_without_bank_match_is_reported_as_unaccounted_customer_evidence():
    snapshot = CaseSnapshot(
        case_id="C",
        revision=1,
        artifacts=[
            ArtifactRef(
                artifact_id="receipt",
                case_id="C",
                kind="receipt",
                mime_type="image/png",
                sha256="a" * 64,
                byte_count=100,
                object_key="aa/" + "a" * 64,
            )
        ],
        segments=[
            Segment(
                segment_id="line",
                artifact_id="receipt",
                text="INR 100 on 2026-10-01 at 11:29 UTR ABC123 to payee@test",
            )
        ],
    )
    for kind, value in [
        ("amount", 10000),
        ("txn_datetime", "2026-10-01T11:29:00+05:30"),
        ("transaction_reference", "ABC123"),
        ("payee_vpa", "payee@test"),
    ]:
        snapshot.claims.append(
            CandidateClaim(
                claim_id=kind,
                kind=kind,
                normalized_value=value,
                anchor_segment_ids=["line"],
                evidence_state="source_supported",
            )
        )
    snapshot.seal()
    approval = Approval(
        approval_id="A",
        case_id="C",
        revision=1,
        digest=snapshot.digest,
        disposition="COMPLETE_HANDOFF",
        reason="Confirmed source, bank match unavailable",
        reviewer=Actor(user_id="R", role="reviewer", tenant_id="demo"),
    )
    report = build_report_update(snapshot, approval)
    assert report["debits"][0]["confirmation"] == "evidence_only_unmatched"
    assert report["debits"][0]["reference"] == "ABC123"
    assert report["unaccounted_amount_minor"] == 10000
    assert report["unaccounted_sources"] and not report["traced_amounts"]


def test_two_crops_of_same_unmatched_payment_do_not_double_the_amount():
    snapshot = CaseSnapshot(case_id="C", revision=1)
    for index in (1, 2):
        id = f"crop-{index}"
        snapshot.artifacts.append(
            ArtifactRef(
                artifact_id=id,
                case_id="C",
                kind="receipt",
                mime_type="image/png",
                sha256=str(index) * 64,
                byte_count=100,
                object_key="aa/" + str(index) * 64,
            )
        )
        snapshot.segments.append(
            Segment(segment_id=id, artifact_id=id, text="INR 100 on 2026-10-01 at 11:29 UTR ABC123")
        )
        for kind, value in [
            ("amount", 10000),
            ("txn_datetime", "2026-10-01T11:29:00+05:30"),
            ("transaction_reference", "ABC123"),
        ]:
            snapshot.claims.append(
                CandidateClaim(
                    claim_id=id + kind,
                    kind=kind,
                    normalized_value=value,
                    anchor_segment_ids=[id],
                    evidence_state="source_supported",
                )
            )
    debits = receipt_debits(snapshot)
    assert len(debits) == 1 and sum(d["amount_minor"] for d in debits) == 10000
    assert len(debits[0]["sources"]) == 6
