from caseproof.domain.contracts import CandidateClaim
from caseproof.domain.ledger import match_ledger


def test_payee_from_second_artifact_does_not_block_first_debit():
    class Bank:
        def transactions(self, account):
            return [
                dict(
                    txn_id=str(i),
                    amount_minor=amount,
                    ts=time,
                    payee=payee,
                    reference=str(i),
                    direction="debit",
                )
                for i, amount, time, payee in [
                    (1, 10000, "2026-10-01T11:29:00+05:30", "first@test"),
                    (2, 20000, "2026-10-01T11:41:00+05:30", "second@test"),
                ]
            ]

    claims = []
    for artifact, amount, time in [("receipt", 10000, "11:29"), ("reply", 20000, "11:41")]:
        for kind, value in [("amount", amount), ("txn_datetime", f"2026-10-01T{time}:00+05:30")]:
            claims.append(
                CandidateClaim(
                    claim_id=artifact + kind,
                    kind=kind,
                    normalized_value=value,
                    anchor_segment_ids=[f"seg-{artifact}-0"],
                    evidence_state="source_supported",
                )
            )
    claims.append(
        CandidateClaim(
            claim_id="payee",
            kind="payee_vpa",
            normalized_value="second@test",
            anchor_segment_ids=["seg-reply-0"],
            evidence_state="source_supported",
        )
    )
    assert {m.txn_id for m in match_ledger(Bank(), "victim", claims)} == {"1", "2"}
