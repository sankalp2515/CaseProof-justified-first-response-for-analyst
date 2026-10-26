import json

from caseproof.domain.clock import rank_queue


def workspace(store, tenant_id, case_id=None, accounts=None):
    from caseproof.api.workspace import describe

    items = store.list_cases(tenant_id)
    if case_id:
        items = [r for r in items if r["case_id"] == case_id]
    metadata = {r["case_id"]: store.metadata(r["case_id"]) for r in items}
    if accounts is not None:
        metadata = {cid: m for cid, m in metadata.items() if m.get("customer_account") in accounts}
    jobs, approvals, outbox = {}, {}, {}
    for cid, meta in metadata.items():
        rows = store.documents.query("jobs", [("case_id", cid)], limit=100)
        if rows:
            jobs[cid] = max(rows, key=lambda r: r["revision"])
        approval = store.approval(cid, meta["revision"])
        if approval:
            approvals[cid, meta["revision"]] = approval.model_dump(mode="json")
        for row in store.documents.query("outbox", [("case_id", cid)], limit=100):
            outbox.setdefault((cid, row["revision"]), []).append(
                {
                    **row,
                    "payload": json.dumps(row["payload"]),
                    "response": json.dumps(row["response"]) if row.get("response") else None,
                }
            )
    records = jobs, approvals, outbox, metadata
    rows = rank_queue([describe(store, store.get(cid), records) for cid in metadata])
    counts = {"total": len(rows)}
    for name in (
        "new",
        "processing",
        "awaiting_information",
        "ready_for_review",
        "approved",
        "completed",
        "needs_attention",
        "failed",
        "needs_analysis",
    ):
        counts[name] = sum(r["status"] == name for r in rows)
    return {"cases": rows, "counts": counts}
