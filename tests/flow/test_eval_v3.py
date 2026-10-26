import json
from copy import deepcopy

import pytest

from caseproof.config import Settings
from eval.v3 import run, score


def test_v3_forbids_mock_and_fallback():
    with pytest.raises(ValueError, match="strict live"):
        run(Settings(_env_file=None, llm_mode="mock"), "B")
    with pytest.raises(ValueError, match="fallback"):
        run(Settings(_env_file=None, allow_fallback=True), "C")


def test_v3_missing_stages_and_trace_errors_remain_in_denominator(tmp_path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs/X.json").write_text(json.dumps({"customer_account": "victim"}))
    expected = {
        "fields": {"amount": 100},
        "acceptable_requests": [],
        "disposition": "COMPLETE_CANDIDATE",
    }
    gold = {
        "case_id": "X",
        "family": "complete",
        "has_followup": True,
        "initial": deepcopy(expected),
        "after_followup": deepcopy(expected),
        "trace_by_account": {"M": 100},
    }
    world = {"transfers": [], "complaint_links": [], "identifiers": []}
    report = score(
        [
            {
                "case_id": "X",
                "stage_id": "initial",
                "failed": True,
                "response_modes": ["live", "cache"],
            }
        ],
        [gold],
        world,
        tmp_path,
    )
    assert report["failed_stages"] == 2
    assert report["field_exact_match"]["total"] == 2
    assert report["trace_account_exact"] == {"correct": 0, "total": 2, "percent": 0.0}
    assert report["stage_modes"] == {"mixed_live_cache": 1}
    assert report["response_modes"] == {"live": 1, "cache": 1}


def test_v3_stops_on_first_provider_failure(tmp_path, monkeypatch):
    from caseproof.adapters.provider import Provider, ProviderError

    root = tmp_path / "kit"
    for folder in ("inputs", "labels", "fixtures"):
        (root / folder).mkdir(parents=True)
    (root / "inputs/manifest.json").write_text(
        json.dumps({"cases": [{"case_id": c, "split": "heldout"} for c in ("X", "Y")]})
    )
    expected = {
        "fields": {"amount": 100},
        "acceptable_requests": [],
        "disposition": "COMPLETE_CANDIDATE",
    }
    for cid in ("X", "Y"):
        (root / f"inputs/{cid}.json").write_text(
            json.dumps(
                {
                    "customer_account": cid,
                    "reported_at": "2026-10-01T12:08:00+05:30",
                    "first_contact": "2026-10-01T11:00:00+05:30",
                    "initial_artifacts": [],
                }
            )
        )
        (root / f"labels/{cid}.json").write_text(
            json.dumps(
                {
                    "case_id": cid,
                    "family": "complete",
                    "initial": deepcopy(expected),
                    "after_followup": deepcopy(expected),
                    "has_followup": False,
                }
            )
        )
    (root / "graph_world.json").write_text(
        json.dumps({"transfers": [], "complaint_links": [], "identifiers": []})
    )
    (root / "trail_feed.json").write_text("[]")
    monkeypatch.setattr("eval.v3.seed_bank", lambda *args: None)
    calls = []

    def fail(self, case_id, *args, **kwargs):
        calls.append(case_id)
        raise ProviderError("LLM_PROVIDER_ERROR")

    monkeypatch.setattr(Provider, "extract_claims", fail)
    settings = Settings(
        _env_file=None,
        llm_mode="live",
        gemini_model="test-model",
        data_dir=tmp_path,
        eval_kit_v3=root,
    )
    result = run(settings, "B")
    assert calls == ["X"]
    assert result["attempted_stages"] == 1 and result["unattempted_stages"] == 1
    assert result["failed_stages"] == 2 and result["status"] == "partial"
    assert result["new_llm_calls"] == 0
