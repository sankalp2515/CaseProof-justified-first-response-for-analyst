from caseproof.domain.contracts import ArtifactRef, CandidateClaim, CaseSnapshot, Segment
from caseproof.domain.evidence import merge_conflicts
from caseproof.domain.selected_payments import independent_receipt_claims


def sample():
    snap = CaseSnapshot(case_id="two", revision=1)
    transactions = []
    for i, amount in enumerate((10000, 23000)):
        aid = f"ART-{i}"
        snap.artifacts.append(
            ArtifactRef(
                artifact_id=aid,
                case_id="two",
                byte_count=10,
                sha256="a" * 64,
                object_key=aid,
                mime_type="image/png",
                kind="receipt",
                stage="initial",
            )
        )
        sid = f"seg-{aid}-0"
        snap.segments.append(Segment(segment_id=sid, artifact_id=aid, text="receipt"))
        reference = f"SYNTH-TX-REF-{i}"
        for kind, value in (
            ("amount", amount),
            ("transaction_reference", reference),
            ("txn_datetime", "2026-10-16"),
        ):
            snap.claims.append(
                CandidateClaim(
                    claim_id=f"{i}-{kind}",
                    kind=kind,
                    normalized_value=value,
                    anchor_segment_ids=[sid],
                    evidence_state="source_supported",
                )
            )
        transactions.append(
            dict(
                txn_id=str(i),
                reference=reference,
                amount_minor=amount,
                payee=f"p{i}@fictional.invalid",
                ts="2026-10-16T12:00:00+05:30",
                direction="debit",
            )
        )
    return snap, transactions


def test_independent_references_do_not_need_an_ocr_time_to_avoid_false_conflicts():
    snap, tx = sample()
    independent = independent_receipt_claims(snap, tx)
    merge_conflicts(snap, independent)
    assert not any(c.evidence_state == "conflicted" for c in snap.claims)
    # Independence is not a ledger match, payment confirmation or recovered time.
    assert snap.ledger_matches == []
    assert {c.normalized_value for c in snap.claims if c.kind == "txn_datetime"} == {"2026-10-16"}


def test_mismatched_amount_is_not_exempted_by_a_correct_reference():
    snap, tx = sample()
    snap.claims[0].normalized_value = 99999
    independent = independent_receipt_claims(snap, tx)
    assert "0-amount" not in independent
    merge_conflicts(snap, independent)
    assert snap.claims[0].evidence_state == "conflicted"


def test_unknown_or_unresolved_reference_cannot_create_independence():
    for state in ("unresolved", "source_supported"):
        snap, tx = sample()
        snap.claims[1].evidence_state = state
        if state == "source_supported":
            snap.claims[1].normalized_value = "SYNTH-TX-UNKNOWN"
        assert "0-amount" not in independent_receipt_claims(snap, tx)


def test_conflicting_payee_or_time_is_not_exempted():
    for kind, value in (
        ("payee_vpa", "other@fictional.invalid"),
        ("txn_datetime", "2026-10-16T23:00:00+05:30"),
    ):
        snap, tx = sample()
        snap.claims.append(
            CandidateClaim(
                claim_id="bad",
                kind=kind,
                normalized_value=value,
                anchor_segment_ids=["seg-ART-0-0"],
                evidence_state="source_supported",
            )
        )
        assert "0-amount" not in independent_receipt_claims(snap, tx)
