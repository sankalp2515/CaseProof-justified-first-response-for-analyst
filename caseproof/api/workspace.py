"""Read-only presentation of existing case, job, approval and delivery records."""

import json

from sqlalchemy import text

from caseproof.domain.clock import current_clock, rank_queue


def describe(store, snapshot, records):
    cid, revision = snapshot.case_id, snapshot.revision
    jobs, approvals, outbox, metadata = records
    job = jobs.get(cid)
    current_job = job if job and job["revision"] == revision else None
    approval = approvals.get((cid, revision))
    if approval and approval["digest"] != snapshot.digest:
        approval = None
    deliveries = []
    historical = []
    for (case, version), entries in outbox.items():
        if case == cid:
            for row in entries:
                if row["status"] == "sent" and row["kind"] != "urgent_referral":
                    payload = json.loads(row["payload"])
                    historical.append(
                        {
                            "revision": version,
                            "kind": row["kind"],
                            "packet_id": payload.get("packet_id"),
                            "response": json.loads(row["response"]) if row["response"] else None,
                        }
                    )
    if approval:
        for row in outbox.get((cid, revision), []):
            payload = json.loads(row["payload"])
            if payload.get("approval_id") == approval["approval_id"]:
                deliveries.append(
                    {
                        "kind": row["kind"],
                        "status": row["status"],
                        "response": json.loads(row["response"]) if row["response"] else None,
                    }
                )
    sent = {r["kind"] for r in deliveries if r["status"] == "sent"}
    if approval:
        status = "completed" if sent == {"case_ticket", "cfcfrms_report_update"} else "approved"
    elif current_job and current_job["status"] in {"queued", "running"}:
        status = "processing"
    elif current_job and current_job["status"] == "failed":
        status = "failed"
    elif any(r.state == "accepted" for r in snapshot.requests):
        status = "awaiting_information"
    elif snapshot.readiness.disposition in {"COMPLETE_CANDIDATE", "ESCALATE_CANDIDATE"}:
        status = "ready_for_review"
    elif not snapshot.artifacts:
        status = "new"
    elif not snapshot.segments or any(
        not any(s.artifact_id == a.artifact_id for s in snapshot.segments)
        for a in snapshot.artifacts
    ):
        status = "needs_analysis"
    else:
        status = "needs_attention"
    clock = current_clock(snapshot)
    from caseproof.domain.freshness import require_fresh_handoff

    stale = False
    if status != "completed":
        try:
            require_fresh_handoff(
                snapshot,
                require_coverage=not approval or approval["disposition"] == "COMPLETE_HANDOFF",
            )
        except ValueError:
            stale = True
            status = "needs_attention"
    bank_amounts = {m.txn_id: m.resolved_fields["amount"] for m in snapshot.ledger_matches}
    bank_amounts.update({u.txn_id: u.amount_minor for u in snapshot.unreported})
    reported = sorted(
        {
            c.normalized_value
            for c in snapshot.claims
            if c.kind == "amount"
            and type(c.normalized_value) is int
            and c.evidence_state not in {"unresolved", "conflicted"}
        }
    )
    from caseproof.domain.brief import build_brief
    from caseproof.domain.contracts import Approval
    from caseproof.domain.ownership import read as read_work
    from caseproof.domain.referral import describe as referral_readiness

    confirmed = sum(m.resolved_fields["amount"] for m in snapshot.ledger_matches)
    candidates = sum(u.amount_minor for u in snapshot.unreported)
    narrative_ids = {a.artifact_id for a in snapshot.artifacts if a.kind == "narrative"}
    narrative = " ".join(s.text for s in snapshot.segments if s.artifact_id in narrative_ids)
    selected_ids = set(metadata[cid].get("selected_transaction_ids", []))
    overlaps = [
        other
        for other, item in metadata.items()
        if other != cid
        and item.get("customer_account") == metadata[cid].get("customer_account")
        and selected_ids.intersection(item.get("selected_transaction_ids", []))
    ]
    return {
        "followup": read_work(store, cid, bool(historical)),
        "delivery_failures": [
            {"kind": r["kind"], "status": r["status"]}
            for r in outbox.get((cid, revision), [])
            if r["status"] in {"failed", "stale", "pending"}
        ],
        "brief": build_brief(snapshot, Approval.model_validate(approval) if approval else None),
        "historical_deliveries": historical,
        "overlapping_complaints": overlaps,
        "victim_summary": narrative[:1000],
        "selected_bank_amount_minor": sum(bank_amounts[t] for t in selected_ids)
        if selected_ids and selected_ids.issubset(bank_amounts)
        else snapshot.trail.get("intake_selected_amount_minor"),
        "confirmed_disputed_minor": confirmed,
        "additional_candidate_minor": candidates,
        "urgent_referral": referral_readiness(snapshot),
        "intake_channel": metadata[cid].get("channel", "employee_assisted"),
        "case_id": cid,
        "revision": revision,
        "digest": snapshot.digest,
        "status": status,
        "readiness": "REVIEW_REQUIRED" if stale else snapshot.readiness.disposition,
        "bank_data_refresh_required": stale,
        "clock": clock.model_dump(),
        "linked_count": len(snapshot.linked),
        "amount_minor": confirmed
        if snapshot.ledger_matches
        else reported[0]
        if len(reported) == 1
        else None,
        "amount_basis": "bank_records" if bank_amounts else "customer_evidence",
        "reported_amounts_minor": reported,
        "artifact_count": len(snapshot.artifacts),
        "reported_at": metadata[cid].get("reported_at"),
        "customer_account": metadata[cid].get("customer_account", ""),
        "job": {key: current_job[key] for key in ("job_id", "revision", "status", "error")}
        if current_job
        else None,
        "approval": approval,
        "deliveries": deliveries,
        "unresolved": snapshot.readiness.unresolved_facts
        + (["bank_data_refresh"] if stale else []),
        "request_pending": any(r.state == "accepted" for r in snapshot.requests),
    }


def workspace(store, tenant_id, case_id=None, accounts=None):
    if getattr(store, "cloud", False):
        from caseproof.cloud.workspace import workspace as cloud_workspace

        return cloud_workspace(store, tenant_id, case_id, accounts)
    # Scope every query to the same tenant. No customer capability uses this endpoint.
    scope = "c.tenant_id=:tenant"
    params = {"tenant": tenant_id}
    if case_id is not None:
        scope += " AND c.case_id=:case_id"
        params["case_id"] = case_id
    elif accounts is not None:
        if not accounts:
            return {"cases": [], "counts": {"total": 0}}
        names = []
        for i, account in enumerate(accounts):
            key = "account_" + str(i)
            params[key] = account
            names.append(":" + key)
        scope += " AND json_extract(c.metadata,'$.customer_account') IN (" + ",".join(names) + ")"
    with store.engine.connect() as db:
        case_rows = db.execute(
            text("SELECT c.case_id,c.metadata FROM cases c WHERE " + scope),
            params,
        ).all()
        jobs = {}
        for row in db.execute(
            text(
                "SELECT j.* FROM jobs j JOIN cases c ON c.case_id=j.case_id "
                "WHERE " + scope + " ORDER BY j.rowid"
            ),
            params,
        ).mappings():
            jobs[row["case_id"]] = dict(row)
        approvals = {
            (r["case_id"], r["revision"]): json.loads(r["data"])
            for r in db.execute(
                text(
                    "SELECT a.* FROM approvals a JOIN cases c ON c.case_id=a.case_id WHERE " + scope
                ),
                params,
            ).mappings()
        }
        outbox = {}
        for row in db.execute(
            text("SELECT o.* FROM outbox o JOIN cases c ON c.case_id=o.case_id WHERE " + scope),
            params,
        ).mappings():
            outbox.setdefault((row["case_id"], row["revision"]), []).append(dict(row))
    metadata = {r[0]: json.loads(r[1]) for r in case_rows}
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
        "needs_analysis",
        "failed",
    ):
        counts[name] = sum(r["status"] == name for r in rows)
    counts["urgent"] = sum(
        r["clock"]["golden_hour_remaining"] is not None
        and r["clock"]["golden_hour_remaining"] > 0
        and r["status"] != "completed"
        for r in rows
    )
    return {"cases": rows, "counts": counts}
