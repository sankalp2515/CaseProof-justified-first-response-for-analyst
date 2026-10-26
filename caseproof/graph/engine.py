"""Finite temporal sop_v1 tracing; all arithmetic uses integer paisa.
Victims first, then clean incoming funds, then own opening funds. Commingled
victims share the REMAINING pool pro-rata, with deterministic largest remainders.
"""

from collections import defaultdict
from dataclasses import dataclass

from caseproof.domain.contracts import hash_json
from caseproof.domain.ledger import dt
from caseproof.graph.contracts import Account, ComplaintLink, Position, TraceResult, Transfer


@dataclass
class Lot:
    tag: str
    amount: int
    path: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


def apportion(weights: dict[str, int], target: int) -> dict[str, int]:
    """Largest-remainder allocation conserving exactly target integer paisa."""
    total = sum(weights.values())
    if not 0 <= target <= total:
        raise ValueError("invalid allocation")
    if not total:
        return {k: 0 for k in weights}
    result = {k: v * target // total for k, v in weights.items()}
    order = sorted(weights, key=lambda k: (-(weights[k] * target % total), k))
    for key in order[: target - sum(result.values())]:
        result[key] += 1
    return result


def trace(
    accounts: list[Account],
    transfers: list[Transfer],
    links: list[ComplaintLink],
    observed_accounts: set[str] | None = None,
) -> TraceResult:
    """Replay once in (timestamp, txn_id) order; cycles require no recursion."""
    nodes = {a.id: a for a in accounts}
    if len(nodes) != len(accounts):
        raise ValueError("duplicate account")
    observed = set(nodes) if observed_accounts is None else observed_accounts
    lots = {a.id: [Lot("OWN", a.opening_balance)] if a.opening_balance else [] for a in accounts}
    roots = defaultdict(list)
    disputed: dict[str, int] = defaultdict(int)
    left = []
    seen = set()
    for link in links:
        identity = (link.complaint_id, link.txn_id)
        if identity in seen:
            raise ValueError("duplicate complaint transfer")
        seen.add(identity)
        roots[link.txn_id].append(link)
        disputed[link.complaint_id] += link.disputed_amount

    def vector(account):
        values = defaultdict(int)
        for lot in lots[account]:
            values[lot.tag] += lot.amount
        return {tag: amount for tag, amount in sorted(values.items()) if amount}

    def remove(account, tag, amount):
        group = [
            (i, item_l)
            for i, item_l in enumerate(lots[account])
            if item_l.tag == tag and item_l.amount
        ]
        weights = {str(i): item_l.amount for i, item_l in group}
        keep = apportion(weights, sum(weights.values()) - amount)
        out = []
        for i, lot in group:
            taken = lot.amount - keep[str(i)]
            lot.amount -= taken
            if taken:
                out.append(Lot(tag, taken, lot.path, lot.sources))
        return out

    processed = set()
    for tx in sorted(transfers, key=lambda t: (dt(t.ts), t.txn_id)):
        if tx.txn_id in processed:
            raise ValueError("duplicate transfer")
        processed.add(tx.txn_id)
        if tx.from_account not in nodes or tx.to_account not in nodes:
            raise ValueError("unknown account")
        if nodes[tx.from_account].kind in ("cashout", "external"):
            raise ValueError("terminal node cannot debit")
        # Reclassify a verified disputed root debit, never create extra money.
        if sum(link.disputed_amount for link in roots[tx.txn_id]) > tx.amount_minor:
            raise ValueError("overclaimed transfer")
        for link in sorted(roots[tx.txn_id], key=lambda item_l: item_l.complaint_id):
            if link.victim != tx.from_account:
                raise ValueError("victim/source mismatch")
            remaining = link.disputed_amount
            for tag in ("CLEAN_IN", "OWN"):
                take = min(remaining, vector(tx.from_account).get(tag, 0))
                if take:
                    remove(tx.from_account, tag, take)
                    lots[tx.from_account].append(Lot(link.complaint_id, take))
                    remaining -= take
            if remaining:
                raise ValueError("disputed funds unavailable")
        before = vector(tx.from_account)
        if tx.amount_minor > sum(before.values()):
            raise ValueError("insufficient source balance")
        victim = {k: v for k, v in before.items() if k not in ("OWN", "CLEAN_IN")}
        debit = tx.amount_minor
        out = []
        take = min(debit, sum(victim.values()))
        kept = apportion(victim, sum(victim.values()) - take)
        for tag in sorted(victim):
            out += remove(tx.from_account, tag, victim[tag] - kept[tag])
        debit -= take
        for tag in ("CLEAN_IN", "OWN"):
            take = min(debit, vector(tx.from_account).get(tag, 0))
            out += remove(tx.from_account, tag, take)
            debit -= take
        terminal = tx.channel.upper() in ("ATM", "CRYPTO") or nodes[tx.to_account].kind in (
            "cashout",
            "external",
        )
        for lot in out:
            moved = Lot(
                "CLEAN_IN" if lot.tag == "OWN" else lot.tag,
                lot.amount,
                lot.path + (tx.txn_id,),
                lot.sources + (tx.source,),
            )
            if terminal:
                left.append((tx.to_account, moved))
            else:
                lots[tx.to_account].append(moved)
    if any(key not in processed for key in roots):
        raise ValueError("complaint references absent transfer")
    positions = []
    for account in sorted(lots):
        for lot in lots[account]:
            if lot.amount and lot.tag not in ("OWN", "CLEAN_IN"):
                state = (
                    "recoverable"
                    if account in observed or nodes[account].kind == "customer"
                    else "unaccounted"
                )
                positions.append(
                    Position(
                        complaint_id=lot.tag,
                        account=account,
                        amount_minor=lot.amount,
                        path=list(lot.path),
                        sources=list(lot.sources),
                        status=state,
                    )
                )
    for account, lot in left:
        if lot.tag not in ("OWN", "CLEAN_IN"):
            positions.append(
                Position(
                    complaint_id=lot.tag,
                    account=account,
                    amount_minor=lot.amount,
                    path=list(lot.path),
                    sources=list(lot.sources),
                    status="left_system",
                )
            )
    positions.sort(key=lambda p: (p.complaint_id, p.account, p.path))
    summaries = {}
    for complaint, amount in sorted(disputed.items()):
        own = [p for p in positions if p.complaint_id == complaint]
        sums = {
            state: sum(p.amount_minor for p in own if p.status == state)
            for state in ("recoverable", "unaccounted", "left_system")
        }
        if sum(sums.values()) != amount:
            raise ValueError("complaint conservation failure")
        summaries[complaint] = {"disputed_amount": amount, **sums}
    vectors = {a: vector(a) for a in sorted(nodes)}
    balances = {a: sum(v.values()) for a, v in vectors.items()}
    total_left = sum(lot.amount for _, lot in left)
    if sum(balances.values()) + total_left != sum(a.opening_balance for a in accounts):
        raise ValueError("money conservation failure")
    result = TraceResult(
        positions=positions,
        account_vectors=vectors,
        balances=balances,
        total_left_system=total_left,
        summaries=summaries,
        feed_sources=sorted({t.source for t in transfers if t.source != "ledger"}),
    )
    result.report_hash = hash_json(result.model_dump(exclude={"report_hash"}))
    return result
