"""Evaluation-only replay gates. Predictions are made before labels are scored."""

import json
from pathlib import Path

from caseproof.pipeline.load import load_input


def initial_input(root, case_id):
    data = load_input(root, case_id)
    return {k: v for k, v in data.items() if k not in ("followup_artifacts", "reply_requests")}


def reveal_v2(root, case_id, catalogue_id):
    from mock_services.customer import response

    return response(root, case_id, catalogue_id)


def reveal_v1(root, case_id, catalogue_id):
    # Mirror the unchanged supplied simulator: gold is consulted only to answer
    # whether the requested response exists, never to choose the model's request.
    root = Path(root)
    gold = json.loads((root / "private_gold" / (case_id + ".json")).read_text(encoding="utf-8"))
    allowed = gold["stages"][0]["acceptable_next_request_ids"]
    if catalogue_id not in allowed:
        return {"available": False, "synthetic": True, "artifacts": []}
    data = load_input(root, case_id)
    return {"available": True, "synthetic": True, "artifacts": data["followup_artifacts"]}
