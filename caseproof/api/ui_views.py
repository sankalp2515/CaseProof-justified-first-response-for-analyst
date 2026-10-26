"""Public demo configuration and the owner's bounded upload/processing receipt."""


def ui_config():
    return {
        "institution": {"name": "Cedar Demo Bank"},
        "synthetic": True,
        "evidence": {
            "max_artifacts": 6,
            "max_file_bytes": 5 * 1024 * 1024,
            "max_case_bytes": 20 * 1024 * 1024,
        },
    }


def victim_receipt(o, cid, snapshot):
    from caseproof.api.workspace import workspace

    meta = o.store.metadata(cid)
    flow = workspace(o.store, meta["tenant_id"], cid)["cases"][0]
    state = (flow.get("job") or {}).get("status", flow["status"])
    message = {
        "queued": "Evidence received. Assessment is queued.",
        "running": "Evidence received. Assessment is running.",
        "failed": "Assessment needs attention. The fraud desk can review or retry it.",
    }.get(state, "Assessment is available to the fraud desk. Check here for questions and updates.")
    return {
        "artifacts": [a.model_dump(exclude={"object_key", "case_id"}) for a in snapshot.artifacts],
        "processing": {"state": state, "message": message},
        "evidence": ui_config()["evidence"],
    }
