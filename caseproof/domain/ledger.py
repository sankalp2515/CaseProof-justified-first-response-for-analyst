from datetime import datetime, timedelta
from typing import Any

from caseproof.domain.contracts import LedgerMatch, UnreportedTransfer
from caseproof.domain.validator import normalized


def dt(value: Any) -> datetime:
    """Parse an ISO timestamp and ensure it has a timezone."""
    d = datetime.fromisoformat(value)
    if d.tzinfo is None:
        from datetime import timezone

        d = d.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
    return d


def match_ledger(bank: Any, account: Any, claims: Any, as_of=None) -> Any:
    """Match supported receipt facts against scoped own-bank debit rows."""
    valid = [
        c
        for c in claims
        if c.evidence_state not in ("unresolved", "conflicted") and c.kind != "embedded_instruction"
    ]
    amounts = [c for c in valid if c.kind == "amount"]
    times = [c for c in valid if c.kind == "txn_datetime" and "T" in str(c.normalized_value)]
    payees = [c for c in valid if c.kind == "payee_vpa"]
    references = [c for c in valid if c.kind == "transaction_reference"]
    groups: dict[tuple, dict[str, tuple[LedgerMatch, bool]]] = {}
    history = bank.transactions(account, as_of) if as_of else bank.transactions(account)
    for tx in history:
        if tx["direction"] != "debit":
            continue
        for a in amounts:
            for t in times:
                if not set(a.anchor_segment_ids) & set(t.anchor_segment_ids) and any(
                    set(a.anchor_segment_ids) & set(other.anchor_segment_ids) for other in times
                ):
                    continue
                # Evidence grouping prevents merging unrelated receipts into one
                # fabricated transfer.
                if not set(a.anchor_segment_ids) & set(t.anchor_segment_ids) and not any(
                    x.split("-")[:-1] == y.split("-")[:-1]
                    for x in a.anchor_segment_ids
                    for y in t.anchor_segment_ids
                ):
                    # Narrative/receipt evidence can supply the time when
                    # there is one reported amount.
                    if len({x.normalized_value for x in amounts}) > 1:
                        continue
                if (
                    int(a.normalized_value) != tx["amount_minor"]
                    or abs((dt(t.normalized_value) - dt(tx["ts"])).total_seconds()) > 600
                ):
                    continue
                transfer_artifacts = {
                    anchor.rsplit("-", 1)[0]
                    for claim in (a, t)
                    for anchor in claim.anchor_segment_ids
                }
                scoped_payees = [
                    p
                    for p in payees
                    if any(
                        anchor.rsplit("-", 1)[0] in transfer_artifacts
                        for anchor in p.anchor_segment_ids
                    )
                ]
                matching_payees = [
                    p
                    for p in scoped_payees
                    if normalized(p.normalized_value) == normalized(tx["payee"])
                ]
                if scoped_payees and not matching_payees:
                    continue
                scoped_references = [
                    r
                    for r in references
                    if any(
                        anchor.rsplit("-", 1)[0] in transfer_artifacts
                        for anchor in r.anchor_segment_ids
                    )
                ]
                local_references = [
                    r
                    for r in scoped_references
                    if set(r.anchor_segment_ids)
                    & (set(a.anchor_segment_ids) | set(t.anchor_segment_ids))
                ]
                matching_references = [
                    r
                    for r in local_references or scoped_references
                    if normalized(r.normalized_value) == normalized(tx["reference"])
                ]
                match = LedgerMatch(
                    claim_ids=[a.claim_id, t.claim_id]
                    + [p.claim_id for p in matching_payees]
                    + [r.claim_id for r in matching_references],
                    txn_id=tx["txn_id"],
                    match_fields=["amount", "txn_datetime"]
                    + (["payee_vpa"] if matching_payees else []),
                    resolved_fields={
                        "amount": tx["amount_minor"],
                        "currency": "INR",
                        "txn_datetime": tx["ts"],
                        "transaction_reference": tx["reference"],
                        "payee_vpa": tx["payee"],
                    },
                )
                # A single amount observation cannot establish two different debits merely
                # by pairing it with unrelated timestamps from other documents.
                group = (a.claim_id,)
                groups.setdefault(group, {})[tx["txn_id"]] = (match, bool(matching_references))
    found: dict[str, LedgerMatch] = {}
    for candidates in groups.values():
        values = list(candidates.values())
        exact = [value for value in values if value[1]]
        choices = exact or values
        if len(choices) == 1:
            match = choices[0][0]
            if match.txn_id in found:
                found[match.txn_id].claim_ids = sorted(
                    set(found[match.txn_id].claim_ids) | set(match.claim_ids)
                )
            else:
                found[match.txn_id] = match
    return list(found.values())


def find_unreported(
    bank: Any, account: Any, first_contact: Any, reported_at: Any, matched_ids: Any, as_of=None
) -> Any:
    """Find unmatched debits within the complaint contact window."""
    start = dt(first_contact) - timedelta(hours=2)
    end = dt(reported_at)
    history = bank.transactions(account, as_of) if as_of else bank.transactions(account)
    flagged = {
        c["payee"]
        for c in bank.complaints((start - timedelta(hours=72)).isoformat(), end.isoformat())
    }
    out = []
    for tx in history:
        if (
            tx["direction"] != "debit"
            or tx["txn_id"] in matched_ids
            or not start <= dt(tx["ts"]) <= end
        ):
            continue
        new = not any(t["payee"] == tx["payee"] and dt(t["ts"]) < start for t in history)
        if new or tx["payee"] in flagged:
            out.append(
                UnreportedTransfer(
                    reference=tx["reference"],
                    txn_id=tx["txn_id"],
                    amount_minor=tx["amount_minor"],
                    payee=tx["payee"],
                    ts=tx["ts"],
                    reason_codes=["new_payee_in_window"] if new else ["complaint_flagged_payee"],
                )
            )
    return out
