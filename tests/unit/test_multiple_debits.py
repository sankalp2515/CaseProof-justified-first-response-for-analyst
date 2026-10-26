from types import SimpleNamespace

import pytest

from caseproof.domain.contracts import CandidateClaim
from caseproof.domain.ledger import match_ledger


@pytest.mark.parametrize("same_artifact", [False, True])
def test_equal_amount_debits_are_resolved_by_their_own_reference_not_cross_matched(same_artifact):
    rows = []
    claims = []
    for i, time in [("A", "10:00"), ("B", "10:05")]:
        rows.append(
            dict(
                txn_id=i,
                amount_minor=10000,
                ts=f"2026-10-15T{time}:00+05:30",
                payee="same@fictional.invalid",
                reference="SYNTH-REF-" + i,
                direction="debit",
            )
        )
        for kind, value in [
            ("amount", 10000),
            ("txn_datetime", rows[-1]["ts"]),
            ("transaction_reference", rows[-1]["reference"]),
        ]:
            claims.append(
                CandidateClaim(
                    claim_id=i + kind,
                    kind=kind,
                    normalized_value=value,
                    anchor_segment_ids=[f"seg-ART-SAME-{i}" if same_artifact else f"seg-ART-{i}-0"],
                    evidence_state="source_supported",
                )
            )
    bank = SimpleNamespace(transactions=lambda account: rows)
    result = match_ledger(bank, "customer", claims)
    assert {m.txn_id for m in result} == {"A", "B"}
    assert all(m.txn_id + "transaction_reference" in m.claim_ids for m in result)
    # One receipt with no reference cannot distinguish these nearby, equal-amount payments.
    ambiguous = [
        c for c in claims if c.claim_id.startswith("A") and c.kind != "transaction_reference"
    ]
    assert match_ledger(bank, "customer", ambiguous) == []


def test_two_transfers_in_one_statement_are_not_discarded_as_one_ambiguous_receipt():
    claims = []
    rows = []
    for i, time, value in [(0, "10:00", 10000), (1, "11:00", 20000)]:
        rows.append(
            dict(
                txn_id=str(i),
                amount_minor=value,
                ts=f"2026-10-15T{time}:00+05:30",
                payee="same@fictional.invalid",
                reference=f"SYNTH-REF-{i}",
                direction="debit",
            )
        )
        for kind, val in [
            ("amount", value),
            ("txn_datetime", rows[-1]["ts"]),
            ("transaction_reference", rows[-1]["reference"]),
        ]:
            claims.append(
                CandidateClaim(
                    claim_id=str(i) + kind,
                    kind=kind,
                    normalized_value=val,
                    anchor_segment_ids=[f"seg-ART-SAME-{i}"],
                    evidence_state="source_supported",
                )
            )
    result = match_ledger(SimpleNamespace(transactions=lambda account: rows), "customer", claims)
    assert {m.txn_id for m in result} == {"0", "1"}


def test_one_amount_and_unrelated_dates_cannot_confirm_two_equal_debits():
    amount = CandidateClaim(
        claim_id="amount",
        kind="amount",
        normalized_value=10000,
        anchor_segment_ids=["seg-RECEIPT-0"],
        evidence_state="source_supported",
    )
    claims = [amount]
    rows = []
    for name, time in [("A", "10:00"), ("B", "11:00")]:
        timestamp = f"2026-10-15T{time}:00+05:30"
        claims.append(
            CandidateClaim(
                claim_id=name + "time",
                kind="txn_datetime",
                normalized_value=timestamp,
                anchor_segment_ids=[f"seg-OTHER-{name}-0"],
                evidence_state="source_supported",
            )
        )
        rows.append(
            dict(
                txn_id=name,
                amount_minor=10000,
                ts=timestamp,
                payee="x@fictional.invalid",
                reference=name,
                direction="debit",
            )
        )
    assert (
        match_ledger(SimpleNamespace(transactions=lambda account: rows), "customer", claims) == []
    )
