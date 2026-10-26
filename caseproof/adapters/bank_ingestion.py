"""Atomic immutable bank imports and explicit debit coverage, isolated from victim evidence."""

import json
from datetime import timedelta

from caseproof.adapters.duckdb_bank import DuckDBBank
from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.domain.contracts import hash_json
from caseproof.domain.ledger import dt
from caseproof.graph.store import GraphStore


class BankIngestion:
    def __init__(self, orchestrator):
        self.o = orchestrator
        self.bank = DuckDBBank(orchestrator.s.duckdb_path)
        self.bank.initialise()
        GraphStore(orchestrator.s.duckdb_path)
        with self.bank.connect() as db:
            for sql in (
                "CREATE TABLE IF NOT EXISTS bank_owners("
                "account VARCHAR PRIMARY KEY,tenant VARCHAR)",
                "CREATE TABLE IF NOT EXISTS bank_customers("
                "account VARCHAR PRIMARY KEY,tenant VARCHAR,data VARCHAR)",
                "CREATE TABLE IF NOT EXISTS bank_imports("
                "batch_id VARCHAR PRIMARY KEY,tenant VARCHAR,digest VARCHAR,data VARCHAR)",
                "CREATE TABLE IF NOT EXISTS bank_coverage(batch_id VARCHAR,account VARCHAR,"
                "start_at VARCHAR,end_at VARCHAR,as_of VARCHAR)",
                "CREATE TABLE IF NOT EXISTS bank_import_targets("
                "batch_id VARCHAR,case_id VARCHAR,PRIMARY KEY(batch_id,case_id))",
            ):
                db.execute(sql)
        from sqlalchemy import text

        with self.o.store.engine.begin() as db:
            db.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS bank_wakeup_ack "
                    "(batch_id TEXT,case_id TEXT,PRIMARY KEY(batch_id,case_id))"
                )
            )
            # Migrate only wakeups with a durable job intent, including completed/stale jobs.
            db.execute(
                text(
                    "INSERT OR IGNORE INTO bank_wakeup_ack "
                    "SELECT substr(a.event,length('bank_imported:')+1),a.case_id "
                    "FROM audit_events a JOIN jobs j ON j.case_id=a.case_id "
                    "AND j.revision=a.revision WHERE a.event LIKE 'bank_imported:%'"
                )
            )

    def check_account(self, account, tenant):
        with self.bank.connect() as db:
            owner = db.execute(
                "SELECT tenant FROM bank_owners WHERE account=?", [account]
            ).fetchone()
        if owner and owner[0] != tenant:
            raise PermissionError("bank account belongs to another tenant")

    def customers(self, tenant):
        with self.bank.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM bank_customers WHERE tenant=? ORDER BY account", [tenant]
                ).fetchall()
            ]

    def coverage(self, account, tenant, start, end, as_of=None):
        self.check_account(account, tenant)
        with self.bank.connect() as db:
            rows = db.execute(
                "SELECT c.batch_id,c.start_at,c.end_at,c.as_of FROM bank_coverage c "
                "JOIN bank_imports i ON c.batch_id=i.batch_id WHERE c.account=? AND i.tenant=?",
                [account, tenant],
            ).fetchall()
        from caseproof.domain.freshness import observation_freshness
        from caseproof.domain.policy import load_policy

        max_age = load_policy(self.o.s.policy_path).get("bank_data_max_age_seconds", 900)
        available = [r for r in rows if not as_of or dt(r[3]) <= dt(as_of)]

        def covered(records):
            cursor, finish = dt(start) - timedelta(hours=2), dt(end)
            used = []
            for row in sorted(records, key=lambda r: (dt(r[1]), -dt(r[3]).timestamp())):
                bid, begin, stop, received = row
                if dt(begin) <= cursor < dt(stop):
                    cursor = dt(stop)
                    used.append(row)
            return cursor >= finish, used

        interval_complete, historical = covered(available)
        fresh = [
            r
            for r in available
            if not as_of or observation_freshness(r[3], as_of, max_age)["state"] == "fresh"
        ]
        complete, used = covered(fresh)
        chosen = used if complete else historical
        observed_at = min((r[3] for r in chosen), key=dt, default=None)
        return {
            "complete": complete,
            "interval_complete": interval_complete,
            "observed_at": observed_at,
            "freshness": observation_freshness(observed_at, as_of, max_age) if as_of else {},
            "batch_ids": sorted({r[0] for r in chosen}),
            "account": account,
            "scope": "own_bank_debits",
            "start": start,
            "end": end,
        }

    def verification(self, account, tenant, start, end, as_of=None):
        with self.bank.connect() as db:
            managed = db.execute(
                "SELECT tenant FROM bank_owners WHERE account=?", [account]
            ).fetchone()
        if managed:
            return self.coverage(account, tenant, start, end, as_of)
        # Internal legacy kit loaders assert a complete fictional bank catalogue. No external
        # import gets this compatibility assertion: imported accounts require explicit intervals.
        return {
            "complete": bool(self.bank.transactions(account)),
            "batch_ids": [],
            "scope": "legacy_synthetic_catalogue",
            "account": account,
        }

    def ingest(self, body, actor):
        if actor.role != "admin" or not self.o.s.demo_mode:
            raise PermissionError("local synthetic bank administrator required")
        data = body.model_dump(mode="json")
        digest = hash_json(data)
        accounts = {c.account for c in body.coverage}
        targets = self.o.store.cases_for_accounts(actor.tenant_id, accounts)
        with self.bank.connect() as db:
            db.begin()
            try:
                prior = db.execute(
                    "SELECT tenant,digest FROM bank_imports WHERE batch_id=?", [body.batch_id]
                ).fetchone()
                if prior:
                    if prior[0] != actor.tenant_id:
                        raise PermissionError("batch belongs to another tenant")
                    if prior[1] != digest:
                        raise ConflictError("bank_batch_id_content_conflict")
                    db.rollback()
                    prior_targets = [
                        r[0]
                        for r in db.execute(
                            "SELECT case_id FROM bank_import_targets WHERE batch_id=?",
                            [body.batch_id],
                        ).fetchall()
                    ]
                    return {
                        "batch_id": body.batch_id,
                        "duplicate": True,
                        "synthetic": True,
                        "reprocess_jobs": self._enqueue(body, actor, prior_targets),
                    }
                for account in body.accounts:
                    owner = db.execute(
                        "SELECT tenant FROM bank_owners WHERE account=?", [account.id]
                    ).fetchone()
                    if owner and owner[0] != actor.tenant_id:
                        raise PermissionError("account belongs to another tenant")
                    values = list(account.model_dump().values())
                    existing = db.execute(
                        "SELECT * FROM trail_accounts WHERE id=?", [account.id]
                    ).fetchone()
                    if existing and not owner:
                        raise ConflictError("cannot_adopt_legacy_bank_account")
                    if existing and list(existing) != values:
                        raise ConflictError("immutable_bank_account_conflict")
                    db.execute("INSERT OR IGNORE INTO trail_accounts VALUES(?,?,?,?,?)", values)
                    db.execute(
                        "INSERT OR IGNORE INTO bank_owners VALUES(?,?)",
                        [account.id, actor.tenant_id],
                    )
                for customer in body.customers:
                    profile = {**customer.model_dump(), "bank": body.bank, "synthetic": True}
                    encoded = json.dumps(profile, sort_keys=True)
                    prior = db.execute(
                        "SELECT data FROM bank_customers WHERE account=?", [customer.account]
                    ).fetchone()
                    if prior and prior[0] != encoded:
                        raise ConflictError("immutable_bank_customer_conflict")
                    db.execute(
                        "INSERT OR IGNORE INTO bank_customers VALUES(?,?,?)",
                        [customer.account, actor.tenant_id, encoded],
                    )
                for tx in body.transactions:
                    values = [
                        getattr(tx, k)
                        for k in (
                            "txn_id",
                            "account",
                            "amount_minor",
                            "payee",
                            "ts",
                            "reference",
                            "direction",
                        )
                    ]
                    prior = db.execute(
                        "SELECT * FROM transactions WHERE txn_id=?", [tx.txn_id]
                    ).fetchone()
                    if prior and (
                        list(prior[:4]) != values[:4]
                        or dt(prior[4].isoformat()) != dt(tx.ts)
                        or list(prior[5:]) != values[5:]
                    ):
                        raise ConflictError("immutable_bank_transaction_conflict")
                    db.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?)", values)
                    observed_at = min(
                        (
                            c.as_of
                            for c in body.coverage
                            if c.account == tx.account and dt(c.start) <= dt(tx.ts) <= dt(c.end)
                        ),
                        key=dt,
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO bank_transaction_observations VALUES(?,?,?,?)",
                        [tx.txn_id, actor.tenant_id, observed_at, body.batch_id],
                    )
                    edge = [
                        tx.txn_id,
                        tx.ts,
                        tx.account,
                        tx.counterparty_account,
                        tx.amount_minor,
                        tx.channel,
                        tx.reference,
                        "ledger",
                    ]
                    prior = db.execute(
                        "SELECT * FROM trail_transfers WHERE txn_id=?", [tx.txn_id]
                    ).fetchone()
                    if prior and list(prior) != edge:
                        raise ConflictError("immutable_bank_edge_conflict")
                    db.execute(
                        "INSERT OR IGNORE INTO trail_transfers VALUES(?,?,?,?,?,?,?,?)", edge
                    )
                for account in body.accounts:
                    if account.kind == "customer":
                        total = db.execute(
                            "SELECT coalesce(sum(amount_minor),0) FROM transactions "
                            "WHERE account=? AND direction='debit'",
                            [account.id],
                        ).fetchone()[0]
                        if total > account.opening_balance:
                            raise ValueError(
                                "synthetic debit history exceeds supplied opening funds"
                            )
                db.execute(
                    "INSERT INTO bank_imports VALUES(?,?,?,?)",
                    [body.batch_id, actor.tenant_id, digest, json.dumps(data)],
                )
                for cid in targets:
                    db.execute(
                        "INSERT INTO bank_import_targets(batch_id,case_id) VALUES(?,?)",
                        [body.batch_id, cid],
                    )
                for cover in body.coverage:
                    db.execute(
                        "INSERT INTO bank_coverage VALUES(?,?,?,?,?)",
                        [body.batch_id, cover.account, cover.start, cover.end, cover.as_of],
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise
        return {
            "batch_id": body.batch_id,
            "duplicate": False,
            "synthetic": True,
            "reprocess_jobs": self._enqueue(body, actor),
        }

    def _enqueue(self, body, actor, targets=None):
        accounts = {c.account for c in body.coverage}
        if targets is None:
            with self.bank.connect() as db:
                targets = [
                    r[0]
                    for r in db.execute(
                        "SELECT case_id FROM bank_import_targets WHERE batch_id=?", [body.batch_id]
                    ).fetchall()
                ]
        jobs = []
        for cid in targets:
            meta = self.o.store.metadata(cid)
            if meta["tenant_id"] != actor.tenant_id or meta.get("customer_account") not in accounts:
                continue
            snapshot = self.o.store.get(cid)
            event = "bank_imported:" + body.batch_id
            from sqlalchemy import text

            with self.o.store.engine.connect() as db:
                prior = db.execute(
                    text("SELECT revision FROM audit_events WHERE case_id=:cid AND event=:e"),
                    {"cid": cid, "e": event},
                ).first()
            if not prior:
                old = snapshot.revision
                snapshot.revision += 1
                snapshot.readiness.disposition = "REVIEW_REQUIRED"
                self.o.store.publish(snapshot, old, event)
                jobs.append(self.o.jobs.enqueue(cid, snapshot.revision))
            elif prior[0] == snapshot.revision:
                jobs.append(self.o.jobs.enqueue(cid, snapshot.revision))
            with self.o.store.engine.begin() as db:
                db.execute(
                    text("INSERT OR IGNORE INTO bank_wakeup_ack VALUES(:b,:c)"),
                    {"b": body.batch_id, "c": cid},
                )
        return jobs

    def recover_wakeups(self):
        from types import SimpleNamespace

        with self.bank.connect() as db:
            batches = db.execute(
                "SELECT i.batch_id,i.data,i.tenant,t.case_id FROM bank_imports i "
                "JOIN bank_import_targets t ON t.batch_id=i.batch_id"
            ).fetchall()
        from sqlalchemy import text

        with self.o.store.engine.connect() as db:
            delivered = set(db.execute(text("SELECT batch_id,case_id FROM bank_wakeup_ack")).all())
        for batch_id, raw, tenant, cid in batches:
            from caseproof.api.bank_contracts import BankBatch

            if (batch_id, cid) not in delivered:
                data = json.loads(raw)
                self._enqueue(
                    BankBatch.model_validate(data), SimpleNamespace(tenant_id=tenant), [cid]
                )
