"""Explicit banking backend selection; no synthetic fallback in the cloud path."""


def bank_services(o, tenant):
    if o.s.runtime_backend == "google":
        from caseproof.adapters.bigquery_bank import BigQueryBank
        from caseproof.domain.policy import load_policy

        bank = BigQueryBank(
            o.bigquery,
            tenant,
            o.store.documents,
            max_age=load_policy(o.s.policy_path).get("bank_data_max_age_seconds", 900),
        )
        return bank, bank
    from caseproof.adapters.bank_ingestion import BankIngestion
    from caseproof.adapters.duckdb_bank import DuckDBBank

    return DuckDBBank(o.s.duckdb_path), BankIngestion(o)


def payment_decisions(o, case_id):
    if o.s.runtime_backend == "google":
        rows = o.store.payment_decisions(case_id)
        return {k: v["disputed"] for k, v in rows.items()}, {k: v["at"] for k, v in rows.items()}
    from sqlalchemy import text

    with o.store.engine.connect() as db:
        exists = db.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='victim_payment_decisions'"
            )
        ).first()
        rows = (
            db.execute(
                text(
                    "SELECT transaction_id,disputed,at FROM victim_payment_decisions "
                    "WHERE case_id=:c"
                ),
                {"c": case_id},
            ).all()
            if exists
            else []
        )
    return {r[0]: r[1] for r in rows}, {r[0]: r[2] for r in rows}
