"""MHA NCRP-CFCFRMS SOP Annexure V, illustrations 1 and 2, pp. 93-96.

June 2026 published copy: see the full PDF source link in docs/ADAPTER_SWAPS.md.
The PDF cover is dated 02.01.2026; June identifies its publication.
"""

from caseproof.graph.contracts import Account, ComplaintLink, Transfer
from caseproof.graph.engine import trace


def run_example(opening, credits, debits):

    accounts = [
        Account(id="M", bank="demo", label="mule", kind="beneficiary", opening_balance=opening),
        Account(id="EXIT", bank="demo", label="ATM", kind="cashout"),
    ]

    transfers = []
    links = []

    for i, (tag, amount) in enumerate(credits):
        accounts.append(
            Account(id=tag, bank="demo", label=tag, kind="customer", opening_balance=amount)
        )

        transfers.append(
            Transfer(
                txn_id=tag,
                ts=f"2026-01-01T{i + 1:02}:00:00Z",
                from_account=tag,
                to_account="M",
                amount_minor=amount,
                channel="UPI",
                reference=tag,
                source="ledger",
            )
        )

        links.append(
            ComplaintLink(
                complaint_id=tag,
                victim=tag,
                txn_id=tag,
                disputed_amount=amount,
                reported_at="2026-01-02T00:00:00Z",
            )
        )

    for order, amount in debits:
        transfers.append(
            Transfer(
                txn_id="D" + str(order),
                ts=f"2026-01-01T{order:02}:30:00Z",
                from_account="M",
                to_account="EXIT",
                amount_minor=amount,
                channel="ATM",
                reference="D",
                source="ledger",
            )
        )

    return trace(accounts, transfers, links)


def test_illustration_1_exact_paisa():

    result = run_example(
        87300, [("A", 9700000), ("B", 5800000), ("C", 15000000)], [(1, 9700000), (2, 5000000)]
    )

    assert result.account_vectors["M"] == {"OWN": 87300, "B": 800000, "C": 15000000}


def test_illustration_2_exact_paisa():

    result = run_example(
        0,
        [("V", 8532600), ("W", 3844300), ("X", 5000000), ("Y", 5000000), ("Z", 3000000)],
        [(6, 4722600)],
    )

    assert result.account_vectors["M"] == {
        "V": 6944697,
        "W": 3128882,
        "X": 4069508,
        "Y": 4069508,
        "Z": 2441705,
    }
