"""Independent Decimal reference allocator. Does NOT import application graph code."""

from collections import defaultdict
from decimal import ROUND_FLOOR, Decimal


def reference_trace(world: dict, observed: set[str]) -> dict:
    """Return complaint/account paisa using independent balance-vector replay."""
    balances = {a["id"]: {"OWN": a["opening_balance"]} for a in world["accounts"]}
    kinds = {a["id"]: a["kind"] for a in world["accounts"]}
    left = defaultdict(lambda: defaultdict(int))
    roots = defaultdict(list)
    for link in world["complaint_links"]:
        roots[link["txn_id"]].append(link)
    for tx in sorted(world["transfers"], key=lambda t: (t["ts"], t["txn_id"])):
        source = balances[tx["from_account"]]
        dest = balances[tx["to_account"]]
        for link in roots[tx["txn_id"]]:
            amount = link["disputed_amount"]
            for tag in ["CLEAN_IN", "OWN"]:
                taking = min(amount, source.get(tag, 0))
                source[tag] = source.get(tag, 0) - taking
                amount -= taking
                source[link["complaint_id"]] = source.get(link["complaint_id"], 0) + taking
            if amount:
                raise ValueError("reference insufficient root funds")
        debit = tx["amount_minor"]
        victims = {k: v for k, v in source.items() if k not in ("OWN", "CLEAN_IN") and v}
        pool = sum(victims.values())
        take = min(debit, pool)
        remaining = pool - take
        removed = {}
        if pool:
            quotas = {
                k: Decimal(v) * Decimal(remaining) / Decimal(pool) for k, v in victims.items()
            }
            retained = {
                k: int(v.to_integral_value(rounding=ROUND_FLOOR)) for k, v in quotas.items()
            }
            priority = sorted(quotas, key=lambda k: (-(quotas[k] - retained[k]), k))
            for k in priority[: remaining - sum(retained.values())]:
                retained[k] += 1
            for k, old in victims.items():
                removed[k] = old - retained[k]
                source[k] = retained[k]
        debit -= take
        for tag in ["CLEAN_IN", "OWN"]:
            taking = min(debit, source.get(tag, 0))
            source[tag] = source.get(tag, 0) - taking
            removed[tag] = taking
            debit -= taking
        if debit:
            raise ValueError("reference overdraft")
        terminal = tx["channel"].upper() in ("ATM", "CRYPTO") or kinds[tx["to_account"]] in (
            "external",
            "cashout",
        )
        for tag, amount in removed.items():
            if terminal:
                left[tx["to_account"]][tag] += amount
            else:
                incoming = "CLEAN_IN" if tag == "OWN" else tag
                dest[incoming] = dest.get(incoming, 0) + amount
    result = {}
    for account, vector in list(balances.items()) + list(left.items()):
        for tag, amount in vector.items():
            if tag not in ("OWN", "CLEAN_IN") and amount:
                result.setdefault(tag, {})[account] = (
                    result.setdefault(tag, {}).get(account, 0) + amount
                )
    return result
