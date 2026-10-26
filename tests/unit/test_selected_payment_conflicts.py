from types import SimpleNamespace as Row

from caseproof.domain.selected_payments import flag_conflicts


def snapshot(amount=999):
    return Row(
        artifacts=[Row(artifact_id="receipt", kind="receipt")],
        segments=[Row(segment_id="line", artifact_id="receipt")],
        claims=[
            Row(
                kind=k,
                normalized_value=v,
                anchor_segment_ids=["line"],
                evidence_state="reported",
                confidence_note="",
            )
            for k, v in [
                ("amount", amount),
                ("payee_vpa", "same@fictional.invalid"),
                ("txn_datetime", "2026-10-16T12:01:00+05:30"),
            ]
        ],
    )


def transactions():
    return [
        {
            "txn_id": "A",
            "reference": "REF-A",
            "payee": "same@fictional.invalid",
            "ts": "2026-10-16T12:00:00+05:30",
            "amount_minor": 500,
        },
        {
            "txn_id": "B",
            "reference": "REF-B",
            "payee": "same@fictional.invalid",
            "ts": "2026-10-16T12:01:00+05:30",
            "amount_minor": 999,
        },
    ]


def test_receipt_for_another_verified_payment_is_not_a_selected_payment_conflict():
    s = snapshot()
    flag_conflicts(s, transactions(), {"A"})
    assert all(c.evidence_state != "conflicted" for c in s.claims)


def test_cropped_receipt_with_no_matching_bank_payment_retains_conflict():
    s = snapshot(777)
    flag_conflicts(s, transactions(), {"A"})
    assert s.claims[0].evidence_state == "conflicted"
