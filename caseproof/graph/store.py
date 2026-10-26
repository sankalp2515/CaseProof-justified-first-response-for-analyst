"""DuckDB graph tables, immutable feed identifiers, and temporal reads."""

import json

from pydantic import BaseModel

from caseproof.adapters.duckdb_bank import DuckDBBank
from caseproof.domain.contracts import hash_json
from caseproof.domain.ledger import dt
from caseproof.graph.contracts import Account, ComplaintLink, Identifier, Transfer


class GraphStore:
    def __init__(self, path: str):
        self.bank = DuckDBBank(path)
        self.bank.initialise()
        with self.bank.connect() as db:
            db.execute(
                (
                    "CREATE TABLE IF NOT EXISTS trail_accounts(id VARCHAR PRIMA"
                    "RY KEY, bank VARCHAR, label VARCHAR, kind VARCHAR, opening"
                    "_balance BIGINT)"
                )
            )
            db.execute(
                (
                    "CREATE TABLE IF NOT EXISTS trail_transfers(txn_id VARCHAR "
                    "PRIMARY KEY,ts VARCHAR,from_account VARCHAR,to_account VAR"
                    "CHAR,amount_minor BIGINT,channel VARCHAR,reference VARCHAR"
                    ",source VARCHAR)"
                )
            )
            db.execute(
                (
                    "CREATE TABLE IF NOT EXISTS trail_complaint_links(complaint"
                    "_id VARCHAR,victim VARCHAR,txn_id VARCHAR,disputed_amount "
                    "BIGINT,reported_at VARCHAR,PRIMARY KEY(complaint_id,txn_id"
                    "))"
                )
            )
            db.execute(
                (
                    "CREATE TABLE IF NOT EXISTS trail_identifiers(entity VARCHA"
                    "R,kind VARCHAR,value VARCHAR,PRIMARY KEY(entity,kind,value"
                    "))"
                )
            )
            db.execute(
                (
                    "CREATE TABLE IF NOT EXISTS trail_updates(update_id VARCHAR"
                    " PRIMARY KEY,digest VARCHAR,data VARCHAR)"
                )
            )

    def load_world(self, world: dict) -> None:
        """Seed graph nodes/own-ledger edges without loading any answer labels."""
        models: list[tuple[str, str, type[BaseModel]]] = [
            ("trail_accounts", "accounts", Account),
            ("trail_transfers", "transfers", Transfer),
            ("trail_complaint_links", "complaint_links", ComplaintLink),
            ("trail_identifiers", "identifiers", Identifier),
        ]
        batches = []
        for table, key, model in models:
            values = [
                list(model(**raw).model_dump().values())
                for raw in world.get(key, [])
                # Downstream knowledge still arrives only through received reports.
                if key != "transfers" or raw.get("source", "ledger") == "ledger"
            ]
            if values:
                batches.append((table, values))
        # Validate before taking the shared writer lock; seed all tables in one
        # transaction, avoiding a durable autocommit for every individual row.
        with self.bank.connect() as db:
            db.begin()
            try:
                for table, values in batches:
                    placeholders = "(" + ",".join("?" for _ in values[0]) + ")"
                    for start in range(0, len(values), 500):
                        batch = values[start:start + 500]
                        db.execute(
                            "INSERT OR IGNORE INTO " + table + " VALUES "
                            + ",".join(placeholders for _ in batch),
                            [value for row in batch for value in row],
                        )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def apply(self, updates: list[dict]) -> None:
        """An update ID is immutable; repeat delivery is harmless."""
        with self.bank.connect() as db:
            db.begin()
            try:
                known = dict(db.execute("SELECT update_id,digest FROM trail_updates").fetchall())
                for row in updates:
                    digest = hash_json(row)
                    old = known.get(row["update_id"])
                    if old:
                        if old != digest:
                            raise ValueError("changed feed update ID")
                        continue
                    for raw in row.get("accounts", []):
                        account = Account.model_validate(raw, strict=True)
                        prior = db.execute(
                            "SELECT * FROM trail_accounts WHERE id=?", [account.id]
                        ).fetchone()
                        if prior and list(prior) != list(account.model_dump().values()):
                            raise ValueError("changed account catalogue identity")
                        db.execute(
                            "INSERT OR IGNORE INTO trail_accounts VALUES(?,?,?,?,?)",
                            list(account.model_dump().values()),
                        )
                    reporter = db.execute(
                        "SELECT bank FROM trail_accounts WHERE id=?", [row["account"]]
                    ).fetchone()
                    if reporter and reporter[0] not in (
                        "Bank not yet reported",
                        row["reporting_bank"],
                    ):
                        raise ValueError("reporting bank does not own this account")
                    if not reporter:
                        db.execute(
                            "INSERT INTO trail_accounts VALUES(?,?,?,?,?)",
                            [row["account"], row["reporting_bank"], row["account"], "layer", 0],
                        )
                    elif reporter[0] == "Bank not yet reported":
                        db.execute(
                            "UPDATE trail_accounts SET bank=? WHERE id=?",
                            [row["reporting_bank"], row["account"]],
                        )
                    for raw in row["credit_received"] + row["onward_transfers"]:
                        tx = Transfer(**raw)
                        for account_id in (tx.from_account, tx.to_account):
                            kind = "layer"
                            if account_id == tx.to_account and tx.channel.upper() in {
                                "ATM",
                                "CRYPTO",
                                "EXTERNAL",
                            }:
                                kind = "cashout"
                            db.execute(
                                "INSERT OR IGNORE INTO trail_accounts VALUES(?,?,?,?,?)",
                                [account_id, "Bank not yet reported", account_id, kind, 0],
                            )
                        existing = db.execute(
                            "SELECT * FROM trail_transfers WHERE txn_id=?", [tx.txn_id]
                        ).fetchone()
                        values = list(tx.model_dump().values())
                        if existing and list(existing) != values:
                            raise ValueError("conflicting transfer source")
                        if not existing:
                            db.execute(
                                "INSERT INTO trail_transfers VALUES(?,?,?,?,?,?,?,?)", values
                            )
                    db.execute(
                        "INSERT INTO trail_updates VALUES(?,?,?)",
                        [row["update_id"], digest, json.dumps(row)],
                    )
                    known[row["update_id"]] = digest
                db.commit()
            except Exception:
                db.rollback()
                raise

    def read(self, as_of: str) -> tuple:
        """Return typed records and latest observed account balances at the instant."""
        with self.bank.connect() as db:

            def rows(table, model):
                cur = db.execute("SELECT * FROM " + table)
                names = [d[0] for d in cur.description]
                return [model(**dict(zip(names, r))) for r in cur.fetchall()]

            accounts = rows("trail_accounts", Account)
            reports = [
                json.loads(r[0]) for r in db.execute("SELECT data FROM trail_updates").fetchall()
            ]
            received = {row["update_id"] for row in reports if dt(row["reported_at"]) <= dt(as_of)}
            late_transactions = {
                r[0]
                for r in db.execute(
                    "SELECT txn_id FROM bank_transaction_observations "
                    "WHERE observed_at>?::TIMESTAMPTZ",
                    [as_of],
                ).fetchall()
            }
            transfers = [
                t
                for t in rows("trail_transfers", Transfer)
                if dt(t.ts) <= dt(as_of)
                and t.txn_id not in late_transactions
                and (t.source == "ledger" or t.source.removeprefix("cfcfrms_update:") in received)
            ]
            ids = {t.txn_id for t in transfers}
            links = [
                item_l
                for item_l in rows(("trail_complaint_links"), ComplaintLink)
                if item_l.txn_id in ids and dt(item_l.reported_at) <= dt(as_of)
            ]
            identifiers = rows("trail_identifiers", Identifier)
            observed = {}
            for row in sorted(reports, key=lambda r: (dt(r["reported_at"]), r["update_id"])):
                if dt(row["reported_at"]) <= dt(as_of):
                    observed[row["account"]] = row
        return accounts, transfers, links, identifiers, observed
