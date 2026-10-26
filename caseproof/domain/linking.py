from datetime import timedelta
from typing import Any

from caseproof.domain.contracts import LinkedComplaint
from caseproof.domain.ledger import dt
from caseproof.domain.validator import normalized


def find_links(bank: Any, payees: Any, callers: Any, reported_at: Any) -> Any:
    """Find related complaints from observed payee or caller identifiers."""
    end = dt(reported_at)
    out = []
    for row in bank.complaints((end - timedelta(hours=72)).isoformat(), end.isoformat()):
        for kind, values, key in [
            ("payee_vpa", payees, "payee"),
            ("caller_number", callers, "caller_number"),
        ]:
            shared = next((v for v in values if normalized(v) == normalized(row[key])), None)
            if shared:
                out.append(
                    LinkedComplaint(
                        complaint_id=row["complaint_id"],
                        link_type=kind,
                        shared_value=shared,
                        reported_at=row["reported_at"],
                        amount_minor=row["amount_minor"],
                    )
                )
                break
    return out
