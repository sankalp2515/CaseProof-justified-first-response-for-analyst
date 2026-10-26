import json

import pytest

from eval.metrics import score_v2
from eval.replay import initial_input, reveal_v2


def test_failed_case_in_denominator():
    gold = [
        {
            "case_id": "X",
            "initial": {
                "fields": {"amount": 100},
                "disposition": "COMPLETE_CANDIDATE",
                "acceptable_requests": [],
                "ledger_ids": [],
                "unreported_ids": [],
                "linked_ids": [],
            },
        }
    ]
    r = score_v2([{"case_id": "X", "stage_id": "initial", "failed": True}], gold)
    assert r["field_exact_match"] == {"correct": 0, "total": 1, "percent": 0.0}
    assert r["failed_stages"] == 1


def test_loader_cannot_read_gold(tmp_path):
    root = tmp_path
    (root / "inputs").mkdir()
    (root / "fixtures").mkdir()
    (root / "inputs" / "X.json").write_text(
        json.dumps(
            {
                "case_id": "X",
                "initial_artifacts": [],
                "followup_artifacts": [{"secret": "future"}],
                "reply_requests": ["x"],
            }
        )
    )
    data = initial_input(root, "X")
    assert "followup_artifacts" not in data
    assert "reply_requests" not in data
    with pytest.raises(ValueError):
        initial_input(root, "../labels/X")


def test_replay_hides_future_artifacts(tmp_path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "X.json").write_text(
        json.dumps(
            {
                "case_id": "X",
                "initial_artifacts": [],
                "followup_artifacts": [{"future": True}],
                "reply_requests": ["allowed"],
            }
        )
    )
    assert reveal_v2(tmp_path, "X", "wrong")["artifacts"] == []
    assert reveal_v2(tmp_path, "X", "allowed")["artifacts"] == [{"future": True}]


def test_arms_share_inputs(tmp_path):
    from eval.arms import input_fingerprint

    (tmp_path / "inputs").mkdir()
    (tmp_path / "fixtures" / "X").mkdir(parents=True)
    (tmp_path / "fixtures" / "X" / "n.txt").write_text("story")
    (tmp_path / "inputs" / "X.json").write_text(
        json.dumps(
            {
                "case_id": "X",
                "initial_artifacts": [
                    {"path": "fixtures/X/n.txt", "kind": "narrative", "mime_type": "text/plain"}
                ],
            }
        )
    )
    assert len({input_fingerprint(tmp_path, "X", arm) for arm in "ABC"}) == 1
