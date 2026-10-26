import importlib.util
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import duckdb
from filelock import FileLock

# DuckDB probes for pandas on every parameterised execute. It is not a dependency,
# and each failed probe walks the whole import path (~2,400 probes and ~12,000
# filesystem stats per practice world). Record the absence once.
if importlib.util.find_spec("pandas") is None:
    sys.modules.setdefault("pandas", None)

_held = threading.local()


class DuckDBBank:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        # DuckDB has one writer process. Serialize short connections across API/worker
        # containers. Nested use on the same thread reuses the held connection: each
        # open costs a cross-process lock plus ~30ms of engine start-up, so a batch of
        # related operations (practice world creation) holds one connection instead.
        # Callers still own their own begin/commit; transactions must not nest.
        held = getattr(_held, "connections", None)
        if held is None:
            held = _held.connections = {}
        key = str(self.path)
        if key in held:
            yield held[key]
            return
        with FileLock(key + ".lock", timeout=60):
            with duckdb.connect(self.path) as connection:
                held[key] = connection
                try:
                    yield connection
                finally:
                    del held[key]

    def initialise(self):
        with self.connect() as db:
            db.begin()
            migrate_observations = not db.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name='bank_transaction_observations'"
            ).fetchone()
            db.execute(
                "CREATE TABLE IF NOT EXISTS bank_transaction_observations("
                "txn_id VARCHAR PRIMARY KEY,tenant VARCHAR,observed_at TIMESTAMPTZ,"
                "batch_id VARCHAR)"
            )
            if (
                migrate_observations
                and db.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name='bank_imports'"
                ).fetchone()
            ):
                import json

                from caseproof.domain.ledger import dt

                for batch_id, tenant, raw in db.execute(
                    "SELECT batch_id,tenant,data FROM bank_imports"
                ).fetchall():
                    body = json.loads(raw)
                    for tx in body["transactions"]:
                        observed = min(
                            (
                                c["as_of"]
                                for c in body["coverage"]
                                if c["account"] == tx["account"]
                                and dt(c["start"]) <= dt(tx["ts"]) <= dt(c["end"])
                            ),
                            key=dt,
                        )
                        db.execute(
                            "INSERT INTO bank_transaction_observations VALUES(?,?,?,?) "
                            "ON CONFLICT(txn_id) DO UPDATE SET "
                            "observed_at=least(bank_transaction_observations.observed_at,"
                            "excluded.observed_at)",
                            [tx["txn_id"], tenant, observed, batch_id],
                        )
            db.execute(
                (
                    "CREATE TABLE IF NOT EXISTS transactions(txn_id VARCHAR PRI"
                    "MARY KEY,account VARCHAR,amount_minor BIGINT,payee VARCHAR"
                    ",ts TIMESTAMPTZ,reference VARCHAR,direction VARCHAR)"
                )
            )
            db.execute(
                (
                    "CREATE TABLE IF NOT EXISTS complaints(complaint_id VARCHAR"
                    " PRIMARY KEY,account VARCHAR,payee VARCHAR,caller_number V"
                    "ARCHAR,reported_at TIMESTAMPTZ,amount_minor BIGINT)"
                )
            )
            db.commit()

    def load(self, transactions, complaints):
        self.initialise()
        with self.connect() as db:
            for table, rows, keys in [
                (
                    "transactions",
                    transactions,
                    ["txn_id", "account", "amount_minor", "payee", "ts", "reference", "direction"],
                ),
                (
                    "complaints",
                    complaints,
                    [
                        "complaint_id",
                        "account",
                        "payee",
                        "caller_number",
                        "reported_at",
                        "amount_minor",
                    ],
                ),
            ]:
                if rows:
                    db.executemany(
                        "INSERT OR REPLACE INTO "
                        + table
                        + " VALUES ("
                        + ",".join("?" for _ in keys)
                        + ")",
                        [[r[k] for k in keys] for r in rows],
                    )

    def query(self, sql, params):
        self.initialise()
        with self.connect() as db:
            cur = db.execute(sql, params)
            keys = [x[0] for x in cur.description]
            rows = [dict(zip(keys, r)) for r in cur.fetchall()]
        for r in rows:
            for k in ["ts", "reported_at"]:
                if k in r:
                    r[k] = r[k].isoformat()
        return rows

    def transactions(self, account, as_of=None):
        from datetime import datetime, timezone

        instant = as_of or datetime.now(timezone.utc).isoformat()
        return self.query(
            "SELECT t.* FROM transactions t LEFT JOIN bank_transaction_observations o "
            "ON t.txn_id=o.txn_id WHERE t.account=? AND t.ts<=?::TIMESTAMPTZ "
            "AND (o.observed_at IS NULL OR o.observed_at<=?::TIMESTAMPTZ) ORDER BY t.ts",
            [account, instant, instant],
        )

    def complaints(self, start, end):
        return self.query(
            "SELECT * FROM complaints WHERE reported_at BETWEEN ?::TIMESTAMPTZ AND ?::TIMESTAMPTZ",
            [start, end],
        )

    def export_csv(self, directory):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        for table in ["transactions", "complaints"]:
            import csv

            with self.connect() as db:
                rows = db.execute("SELECT * FROM " + table)
                header = [x[0] for x in rows.description]
                values = rows.fetchall()
            with (root / (table + ".csv")).open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(values)
