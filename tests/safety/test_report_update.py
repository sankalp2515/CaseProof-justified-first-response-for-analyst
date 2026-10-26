import pytest

from caseproof.domain.contracts import Actor, Approval, CaseSnapshot, ClockState, LedgerMatch
from caseproof.domain.report_update import build_report_update


def test_every_debit_and_traced_number_has_source_and_exact_revision():
    s = CaseSnapshot(
        case_id="X",
        revision=3,
        clock=ClockState(
            first_debit_at="2026-01-01T11:29:00Z",
            as_of="2026-01-01T12:08:00Z",
            minutes_since_first_debit=39,
            golden_hour_remaining=21,
        ),
        ledger_matches=[
            LedgerMatch(
                claim_ids=["C"],
                txn_id="T1",
                match_fields=["amount"],
                resolved_fields=dict(
                    amount=4827400,
                    transaction_reference="REF1",
                    payee_vpa="safe@fictional.invalid",
                    txn_datetime="2026-01-01T11:29:00Z",
                ),
            ),
            LedgerMatch(
                claim_ids=["F"],
                txn_id="T2",
                match_fields=["amount"],
                resolved_fields=dict(
                    amount=2500000,
                    transaction_reference="REF2",
                    payee_vpa="refund@fictional.invalid",
                    txn_datetime="2026-01-01T11:41:00Z",
                ),
            ),
        ],
        trail=dict(
            positions=[
                dict(
                    account="M",
                    amount_minor=100000,
                    path=["T1"],
                    sources=["ledger"],
                    status="recoverable",
                    observation_source="cfcfrms_update:U1",
                )
            ],
            summary=dict(recoverable=100000, left_system=0, unaccounted=0),
            report_hash="h",
            transfers=[dict(txn_id="T1", source="ledger")],
            account_observations=[dict(update_id="U1", account="M", balance_minor=100000)],
        ),
    ).seal()
    a = Approval(
        approval_id="A",
        case_id="X",
        revision=3,
        digest=s.digest,
        disposition="COMPLETE_HANDOFF",
        reviewer=Actor(user_id="r", role="reviewer", tenant_id="demo"),
        reason="review",
        clock_at_approval=s.clock,
    )
    report = build_report_update(s, a)
    assert {d["txn_id"] for d in report["debits"]} == {"T1", "T2"}
    assert all(d["sources"] for d in report["debits"])
    assert report["revision"] == 3 and report["digest"] == s.digest
    assert report["unaccounted_amount_minor"] + sum(
        p["amount_minor"] for p in report["traced_amounts"]
    ) == sum(d["amount_minor"] for d in report["debits"])
    assert report["traced_amounts"][0]["path"] == ["T1"]
    assert report["clock"]["golden_hour_remaining"] == 21
    s.revision = 4
    with pytest.raises(ValueError):
        build_report_update(s, a)


def test_trail_number_without_source_cannot_export():
    from caseproof.domain.report_update import validate_trail_sources

    with pytest.raises(ValueError):
        validate_trail_sources({"positions": [dict(amount_minor=1, path=[], sources=[])]})


def test_unconfirmed_debit_keeps_known_ledger_reference():
    from caseproof.domain.contracts import UnreportedTransfer

    snapshot = CaseSnapshot(
        case_id="X",
        revision=1,
        unreported=[
            UnreportedTransfer(
                txn_id="T2",
                amount_minor=2500000,
                reference="KNOWN-LEDGER-REFERENCE",
                payee="refund@fictional.invalid",
                ts="2026-10-01T11:41:00+05:30",
                reason_codes=["new_payee_in_window"],
            )
        ],
    ).seal()
    approval = Approval(
        approval_id="A",
        case_id="X",
        revision=1,
        digest=snapshot.digest,
        disposition="ESCALATE_WITH_GAPS",
        reason="Unconfirmed debit retained",
        reviewer=Actor(user_id="R", role="reviewer", tenant_id="demo"),
    )
    debit = build_report_update(snapshot, approval)["debits"][0]
    assert debit["reference"] == "KNOWN-LEDGER-REFERENCE"
    assert debit["sources"] == ["ledger:T2"]
