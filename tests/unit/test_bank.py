from caseproof.adapters.duckdb_bank import DuckDBBank
from caseproof.domain.contracts import CandidateClaim
from caseproof.domain.ledger import find_unreported, match_ledger
from caseproof.domain.linking import find_links


def bank(tmp_path):
    b = DuckDBBank(str(tmp_path / "bank.duckdb"))
    b.initialise()
    b.load(
        [
            dict(
                txn_id="T1",
                account="A",
                amount_minor=4827400,
                payee="safe-account@fictional.invalid",
                ts="2026-10-01T11:29:00+05:30",
                reference="SYNTH-TX-0009",
                direction="debit",
            ),
            dict(
                txn_id="T2",
                account="A",
                amount_minor=2500000,
                payee="refund-desk@fictional.invalid",
                ts="2026-10-01T11:41:00+05:30",
                reference="SYNTH-TX-SECOND",
                direction="debit",
            ),
            dict(
                txn_id="B1",
                account="A",
                amount_minor=10000,
                payee="grocer@fictional.invalid",
                ts="2026-09-20T11:00:00+05:30",
                reference="SYNTH-TX-B1",
                direction="debit",
            ),
            dict(
                txn_id="B2",
                account="A",
                amount_minor=10000,
                payee="grocer@fictional.invalid",
                ts="2026-10-01T11:10:00+05:30",
                reference="SYNTH-TX-B2",
                direction="debit",
            ),
        ],
        [
            dict(
                complaint_id="C1",
                account="OTHER",
                payee="safe-account@fictional.invalid",
                caller_number="+91 00000 04417",
                reported_at="2026-10-01T10:00:00+05:30",
                amount_minor=10000,
            )
        ],
    )
    return b


def claims():
    return [
        CandidateClaim(claim_id=k, kind=k, normalized_value=v, anchor_segment_ids=["s"])
        for k, v in [
            ("amount", 4827400),
            ("txn_datetime", "2026-10-01T11:29:00+05:30"),
            ("payee_vpa", "safe-account@fictional.invalid"),
        ]
    ]


def test_ledger_resolves_reference(tmp_path):
    m = match_ledger(bank(tmp_path), "A", claims())
    assert m[0].resolved_fields["transaction_reference"] == "SYNTH-TX-0009"


def test_unreported_transfer_found(tmp_path):
    b = bank(tmp_path)
    u = find_unreported(b, "A", "2026-10-01T11:00:00+05:30", "2026-10-01T12:00:00+05:30", ["T1"])
    assert "T2" in [x.txn_id for x in u]


def test_routine_payment_not_flagged(tmp_path):
    b = bank(tmp_path)
    u = find_unreported(b, "A", "2026-10-01T11:00:00+05:30", "2026-10-01T12:00:00+05:30", ["T1"])
    assert "B2" not in [x.txn_id for x in u]


def test_linked_by_payee(tmp_path):
    assert (
        find_links(
            bank(tmp_path), ["safe-account@fictional.invalid"], [], "2026-10-01T12:00:00+05:30"
        )[0].link_type
        == "payee_vpa"
    )


def test_linked_by_caller_number(tmp_path):
    assert (
        find_links(bank(tmp_path), [], ["+91 00000 04417"], "2026-10-01T12:00:00+05:30")[
            0
        ].link_type
        == "caller_number"
    )


def test_other_bank_transfer_not_in_ledger_requires_customer(tmp_path):
    assert not match_ledger(bank(tmp_path), "OTHER_BANK", claims())
