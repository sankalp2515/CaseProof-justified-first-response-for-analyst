"""Customer simulator alone decides whether a request releases followup artifacts."""

import json
from pathlib import Path

from caseproof.domain.actions import request_state
from caseproof.pipeline.load import read_artifact


def response(root, case_id, catalogue_id):
    data = json.loads((Path(root) / "inputs" / (case_id + ".json")).read_text(encoding="utf-8"))
    if catalogue_id not in data.get("reply_requests", []):
        return {"synthetic": True, "available": False, "artifacts": []}
    return {"synthetic": True, "available": True, "artifacts": data["followup_artifacts"]}


def reply(o, root, case_id, request_id, investigate=True):
    snap = o.store.get(case_id)
    request = next(r for r in snap.requests if r.request_id == request_id)
    if request.state == "proposed":
        request_state(o, case_id, request_id, "accepted")
    sim = response(
        root, o.store.metadata(case_id).get("kit_case_id", case_id), request.catalogue_id
    )
    if not sim["available"]:
        request_state(
            o,
            case_id,
            request_id,
            "unavailable",
            "Synthetic customer has no response artifact for this request",
        )
        return o.process(case_id, investigate=investigate)
    for item in sim["artifacts"]:
        o.intake.add(
            case_id,
            read_artifact(root, item),
            item["mime_type"],
            item["kind"],
            stage="followup",
            artifact_id=item["artifact_id"],
        )
    request_state(o, case_id, request_id, "fulfilled")
    return o.process(case_id, investigate=investigate)
