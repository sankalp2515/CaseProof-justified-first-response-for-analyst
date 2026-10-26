import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from caseproof.adapters.provider import Provider
from caseproof.config import Settings
from caseproof.domain.contracts import CandidateClaim
from caseproof.domain.facts import merge_facts
from caseproof.pipeline.load import load_case
from caseproof.pipeline.orchestrator import Orchestrator


def test_no_label_fields_reach_app(tmp_path):
    root = tmp_path / "kit"
    (root / "inputs").mkdir(parents=True)
    (root / "fixtures").mkdir()
    (root / "inputs" / "X.json").write_text(
        json.dumps(
            dict(
                case_id="X",
                scenario="legitimate_payment",
                family="test",
                split="heldout",
                unavailable_reason="label only",
                initial_artifacts=[],
            )
        )
    )
    s = Settings(
        _env_file=None,
        llm_mode="mock",
        data_dir=tmp_path,
        object_dir=tmp_path / "obj",
        sqlite_url="sqlite:///" + str(tmp_path / "db.sqlite"),
    )
    o = Orchestrator(s)
    load_case(o, root, "X")
    keys = set(o.store.metadata("X")) - {"revision", "tenant_id"}
    assert keys <= {
        "customer_account",
        "reported_at",
        "first_contact",
        "kit_case_id",
        "unavailable_reason",
    }
    assert not o.store.metadata("X").get("unavailable_reason")


def failing(tmp_path, allow=False):
    p = Provider(Settings(_env_file=None, llm_mode="mock", data_dir=tmp_path, allow_fallback=allow))
    p.mode = "live"
    p.generate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret details"))
    return p


def test_live_fails_loudly(tmp_path):
    with pytest.raises(RuntimeError, match="LLM_PROVIDER_ERROR"):
        failing(tmp_path).extract_claims("C", 1, [])


def test_explicit_dev_fallback_labelled(tmp_path):
    r = failing(tmp_path, True).extract_claims("C", 1, [])
    assert r.run.mode == "mock" and "fallback" in r.run.model_id


def test_live_eval_rejects_fallback(tmp_path):
    from eval.run import run

    with pytest.raises(ValueError, match="fallback"):
        run(
            Settings(_env_file=None, llm_mode="live", allow_fallback=True, data_dir=tmp_path),
            "C",
            "dev",
            "v2",
        )


def test_fact_merges_values_across_sources():
    cs = [
        CandidateClaim(
            claim_id=str(i),
            kind="amount",
            normalized_value=10000,
            anchor_segment_ids=[str(i)],
            evidence_state=state,
        )
        for i, state in enumerate(["reported", "source_supported"])
    ]
    facts = merge_facts(cs)
    assert len(facts) == 1 and len(facts[0].sources) == 2 and len(facts[0].states) == 2


def test_cli_from_another_directory(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    env["LLM_MODE"] = "mock"
    r = subprocess.run(
        [sys.executable, "-m", "caseproof.cli", "smoke"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and "mock" in r.stdout
    from caseproof.domain.policy import load_policy

    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert load_policy()["version"]
    finally:
        os.chdir(old)


def test_legacy_stored_metadata_is_sanitized_without_rewriting_snapshots(tmp_path):
    from sqlalchemy import text

    from caseproof.adapters.sqlite_casestore import CaseStore

    url = "sqlite:///" + str(tmp_path / "cases.sqlite")
    store = CaseStore(url)
    snapshot = store.create("legacy", customer_account="victim")
    with store.engine.begin() as db:
        db.execute(
            text("UPDATE cases SET metadata=:value WHERE case_id=:id"),
            {
                "value": json.dumps(
                    {
                        "customer_account": "victim",
                        "scenario": "answer",
                        "family": "private",
                        "split": "heldout",
                    }
                ),
                "id": "legacy",
            },
        )
    store = CaseStore(url)
    with store.engine.connect() as db:
        raw = db.execute(text("SELECT metadata FROM cases")).scalar_one()
    assert json.loads(raw) == {"customer_account": "victim"}
    assert store.get("legacy").digest == snapshot.digest
