"""Join authoritative own-ledger roots to sourced downstream reports."""

from typing import Any

from caseproof.adapters.local_trail_feed import LocalTrailFeed
from caseproof.domain.contracts import LinkedComplaint
from caseproof.domain.ledger import dt
from caseproof.graph.contracts import ComplaintLink
from caseproof.graph.engine import trace
from caseproof.graph.store import GraphStore


def locate(o: Any, snapshot: Any) -> None:
    """Attach only this complaint's positions; other taints are internal arithmetic."""
    meta = o.store.metadata(snapshot.case_id)
    store: Any
    feed: Any
    if o.s.runtime_backend == "google":
        from caseproof.adapters.bank_factory import bank_services
        from caseproof.adapters.bigquery_graph import BigQueryGraph

        bank, _ = bank_services(o, meta["tenant_id"])
        store = BigQueryGraph(bank)
    else:
        store = GraphStore(o.s.duckdb_path)
    if o.s.runtime_backend == "google":
        feed = None
    elif o.s.trail_feed_url:
        from caseproof.adapters.http_trail_feed import HTTPTrailFeed

        feed = HTTPTrailFeed(o.s.trail_feed_url)
    else:
        feed = LocalTrailFeed(o.s.trail_feed_path)
    updates = feed.load(snapshot.clock.as_of) if feed is not None else []
    store.apply(updates)
    accounts, transfers, links, identifiers, observed = store.read(snapshot.clock.as_of)
    meta = o.store.metadata(snapshot.case_id)
    victim = meta.get("customer_account", "")
    if o.s.runtime_backend == "google":
        # Current-case roots come from its own matched disputes, never another
        # complaint by the same victim about overlapping bank transactions.
        links = [link for link in links if link.victim != victim]
    own_links = [item_l for item_l in links if item_l.victim == victim]
    # Fresh complaints need no preloaded complaint/answer fixture: establish roots from the
    # independent own-bank transactions actually matched or discovered in this assessment.
    if not own_links:
        if not any(a.id == victim and a.kind == "customer" for a in accounts):
            # A feed may mention a victim account but cannot create an own-bank
            # opening balance or establish bank catalogue authority for it.
            snapshot.trail = {}
            return
        roots = (
            {m.txn_id for m in snapshot.ledger_matches} | {t.txn_id for t in snapshot.unreported}
            if meta.get("channel") != "bank_website"
            else {m.txn_id for m in snapshot.ledger_matches}
        )
        own_links = [
            ComplaintLink(
                complaint_id=snapshot.case_id,
                victim=victim,
                txn_id=t.txn_id,
                disputed_amount=t.amount_minor,
                reported_at=meta["reported_at"],
            )
            for t in transfers
            if t.txn_id in roots and t.from_account == victim and t.source == "ledger"
        ]
        links = links + own_links
    if not own_links:
        snapshot.trail = {}
        return
    # Other banks' unrelated reports can be partial. Only reconcile the connected
    # money component for this victim; still retain all roots sharing that component.
    all_links, all_transfers = links, transfers
    adjacency: dict[str, set[str]] = {}
    for tx in transfers:
        adjacency.setdefault(tx.from_account, set()).add(tx.to_account)
        adjacency.setdefault(tx.to_account, set()).add(tx.from_account)
    reached, frontier = {victim}, [victim]
    while frontier:
        for target in adjacency.get(frontier.pop(), set()) - reached:
            reached.add(target)
            frontier.append(target)
    accounts = [a for a in accounts if a.id in reached]
    transfers = [t for t in transfers if t.from_account in reached and t.to_account in reached]
    transaction_ids = {t.txn_id for t in transfers}
    links = [link for link in links if link.txn_id in transaction_ids]
    observed = {account: row for account, row in observed.items() if account in reached}
    from caseproof.adapters.bank_factory import bank_services

    bank, _ = bank_services(o, meta["tenant_id"])
    for link in links:
        tx = next(t for t in transfers if t.txn_id == link.txn_id)
        if tx.source == "ledger":
            proof = next(
                (
                    r
                    for r in bank.transactions(link.victim, snapshot.clock.as_of)
                    if r["txn_id"] == tx.txn_id
                ),
                None,
            )
            if (
                not proof
                or proof["amount_minor"] != tx.amount_minor
                or dt(proof["ts"]) != dt(tx.ts)
            ):
                raise ValueError("first hop has no matching own-ledger row")
    from caseproof.domain.freshness import observation_freshness
    from caseproof.domain.policy import load_policy

    max_age = load_policy(o.s.policy_path).get("bank_data_max_age_seconds", 900)
    fresh = {
        account
        for account, row in observed.items()
        if observation_freshness(row["reported_at"], snapshot.clock.as_of, max_age)["state"]
        == "fresh"
    }
    result = trace(accounts, transfers, links, fresh)
    complaints = {item_l.complaint_id for item_l in own_links}
    for account, row in observed.items():
        if result.balances.get(account) != row["balance_minor"]:
            raise ValueError("reported balance does not reconcile")
    positions = [p for p in result.positions if p.complaint_id in complaints]
    summary = {
        state: sum(p.amount_minor for p in positions if p.status == state)
        for state in ("recoverable", "unaccounted", "left_system")
    }
    used = {tid for p in positions for tid in p.path}
    snapshot.trail = {
        "rule": "sop_v1",
        "positions": [
            {
                **p.model_dump(),
                "availability_note": "Latest bank observation is stale; refresh required"
                if p.account in observed and p.account not in fresh
                else "No bank balance observation"
                if p.status == "unaccounted"
                else "Potential availability at the reported time; not a confirmed recovery",
                "observation_source": "cfcfrms_update:" + observed[p.account]["update_id"]
                if p.status == "recoverable" and p.account in observed
                else None,
            }
            for p in positions
        ],
        "account_observations": [
            {
                "update_id": row["update_id"],
                "account": row["account"],
                "reporting_bank": row["reporting_bank"],
                "reported_at": row["reported_at"],
                "balance_minor": row["balance_minor"],
                "freshness": observation_freshness(
                    row["reported_at"], snapshot.clock.as_of, max_age
                ),
            }
            for account, row in observed.items()
            if account in {p.account for p in positions}
        ],
        "summary": summary,
        "report_hash": result.report_hash,
        "transfers": [t.model_dump() for t in transfers if t.txn_id in used],
        "accounts": [
            a.model_dump()
            for a in accounts
            if a.id in {p.account for p in positions}
            or a.id in {t.from_account for t in transfers if t.txn_id in used}
        ],
        "feed_sources": result.feed_sources,
    }
    snapshot.clock.recoverable_now = summary["recoverable"]
    snapshot.linked = graph_links(victim, all_links, all_transfers, identifiers, snapshot.linked)


def graph_links(
    victim: Any, links: Any, transfers: Any, identifiers: Any, existing: Any
) -> list[LinkedComplaint]:
    """Find shared payee/caller/device associations up to two complaint hops."""
    entities = {item_l.complaint_id: {item_l.victim} for item_l in links}
    for link in links:
        tx = next(t for t in transfers if t.txn_id == link.txn_id)
        entities.setdefault(link.complaint_id, set()).add(tx.to_account)
    features = {
        cid: {(i.kind, i.value) for i in identifiers if i.entity in members}
        | {("payee_vpa", m) for m in members}
        for cid, members in entities.items()
    }
    seeds = {item_l.complaint_id for item_l in links if item_l.victim == victim}
    reached = set(seeds)
    out = {item_l.complaint_id: item_l for item_l in existing}
    for _ in range(2):
        frontier = set()
        for target, values in features.items():
            if target in reached:
                continue
            shared = next(
                (
                    v
                    for source in sorted(reached)
                    for v in sorted(values & features.get(source, set()))
                ),
                None,
            )
            if shared:
                link = next(item_l for item_l in links if item_l.complaint_id == target)
                kind, value = shared
                out[target] = LinkedComplaint(
                    complaint_id=target,
                    link_type=kind if kind in ("caller_number", "device") else "payee_vpa",
                    shared_value=value,
                    reported_at=link.reported_at,
                    amount_minor=link.disputed_amount,
                )
                frontier.add(target)
        reached |= frontier
    return sorted(out.values(), key=lambda item_l: item_l.complaint_id)
