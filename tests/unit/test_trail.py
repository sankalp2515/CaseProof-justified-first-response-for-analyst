from hypothesis import given, settings
from hypothesis import strategies as st

from caseproof.graph.contracts import Account, ComplaintLink, Transfer
from caseproof.graph.engine import trace


@given(
    st.lists(st.integers(min_value=1, max_value=100000), min_size=1, max_size=6),
    st.integers(min_value=0, max_value=100000),
)
@settings(max_examples=60, deadline=None)
def test_conservation_nonnegative_determinism_and_cycles(credits, requested):
    total = sum(credits)
    amount = min(total, requested)
    accounts = [
        Account(id="M", bank="d", label="m", kind="beneficiary"),
        Account(id="L", bank="d", label="l", kind="layer"),
    ]
    tx = []
    links = []
    for i, v in enumerate(credits):
        tag = str(i)
        accounts.append(Account(id=tag, bank="d", label=tag, kind="customer", opening_balance=v))
        tx.append(
            Transfer(
                txn_id="T" + tag,
                ts=f"2026-01-01T00:{i:02}:00Z",
                from_account=tag,
                to_account="M",
                amount_minor=v,
                channel="UPI",
                reference=tag,
                source="ledger",
            )
        )
        links.append(
            ComplaintLink(
                complaint_id=tag,
                victim=tag,
                txn_id="T" + tag,
                disputed_amount=v,
                reported_at="2026-01-01T01:00:00Z",
            )
        )
    if amount:
        for tid, src, dst, minute in [("OUT", "M", "L", 20), ("BACK", "L", "M", 21)]:
            tx.append(
                Transfer(
                    txn_id=tid,
                    ts=f"2026-01-01T00:{minute}:00Z",
                    from_account=src,
                    to_account=dst,
                    amount_minor=amount,
                    channel="UPI",
                    reference=tid,
                    source="ledger",
                )
            )
    r = trace(accounts, tx, links)
    assert sum(r.balances.values()) + r.total_left_system == total
    assert all(v >= 0 for vector in r.account_vectors.values() for v in vector.values())
    assert all(sum(r.account_vectors[a].values()) == b for a, b in r.balances.items())
    assert r.report_hash == trace(accounts, list(reversed(tx)), links).report_hash
    assert sum(p.amount_minor for p in r.positions) == total
