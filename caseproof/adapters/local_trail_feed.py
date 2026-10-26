"""Read immutable simulated CFCFRMS layer updates from local JSON."""

import json
from pathlib import Path

from caseproof.domain.ledger import dt
from caseproof.graph.contracts import Account, Transfer


class LocalTrailFeed:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, as_of: str) -> list[dict]:
        """Only return updates received by the replay/wall-clock instant."""
        if not self.path.exists():
            return []
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        return validate_updates(rows, as_of)


def validate_updates(rows: list[dict], as_of: str) -> list[dict]:
    """Validate immutable downstream update contracts for file and HTTP transport."""
    out = []
    for row in rows:
        if not all(
            isinstance(row.get(k), str) and row[k]
            for k in ("update_id", "account", "reporting_bank", "reported_at")
        ):
            raise ValueError("missing bank update identity")
        if type(row.get("balance_minor")) is not int:
            raise ValueError("bank balance must be integer paisa")
        for account in row.get("accounts", []):
            Account.model_validate(account, strict=True)
        if dt(row["reported_at"]) > dt(as_of):
            continue
        if int(row["balance_minor"]) < 0:
            raise ValueError("negative bank-reported balance")
        for item in row["credit_received"] + row["onward_transfers"]:
            tx = Transfer.model_validate(item, strict=True)
            if item in row["credit_received"] and tx.to_account != row["account"]:
                raise ValueError("credit does not belong to reporting account")
            if item in row["onward_transfers"] and tx.from_account != row["account"]:
                raise ValueError("debit does not belong to reporting account")
            if dt(tx.ts) > dt(row["reported_at"]):
                raise ValueError("future transfer in bank report")
            if (
                item in row["onward_transfers"]
                and tx.source != "cfcfrms_update:" + row["update_id"]
            ):
                raise ValueError("feed source mismatch")
        out.append(row)
    return sorted(out, key=lambda r: (dt(r["reported_at"]), r["update_id"]))
