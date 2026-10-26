import json
from datetime import datetime

from caseproof.config import Settings
from caseproof.pipeline.load import load_case
from caseproof.pipeline.orchestrator import Orchestrator
from kitgen.v3 import generate
from mock_services.customer import reply


def test_extended_gold_and_unique_images(tmp_path):
    root = tmp_path / "kit"
    bank = str(tmp_path / "bank.duckdb")
    card = generate(root, bank)
    assert 30 <= card["case_count"] <= 40
    assert card["unique_image_ratio"] >= 0.9
    o = Orchestrator(
        Settings(
            _env_file=None,
            llm_mode="mock",
            data_dir=tmp_path,
            sqlite_url="sqlite:///" + str(tmp_path / "cases.sqlite"),
            object_dir=tmp_path / "obj",
            duckdb_path=bank,
            trail_feed_path=root / "trail_feed.json",
        )
    )
    o.clock_as_of = datetime.fromisoformat("2026-10-01T12:08:00+05:30")
    load_case(o, root, "GOLD-001")
    initial = o.process("GOLD-001")
    assert initial.clock.golden_hour_remaining == 21
    assert initial.trail["summary"]["left_system"] > 0
    # Reports at 11:46-11:48 are stale at 12:08 under the explicit 15-minute policy.
    assert initial.trail["summary"]["recoverable"] == 0
    assert initial.trail["summary"]["unaccounted"] > 2500000
    assert sum(initial.trail["summary"].values()) == 7327400
    truth = json.loads((root / "labels/GOLD-001.json").read_text())
    totals = {}
    for p in initial.trail["positions"]:
        totals[p["account"]] = totals.get(p["account"], 0) + p["amount_minor"]
    assert totals == truth["trace_by_account"]
    assert initial.requests[0].catalogue_id == "confirm_additional_transfer"
    after = reply(o, root, "GOLD-001", initial.requests[0].request_id)
    assert after.readiness.disposition == "COMPLETE_CANDIDATE"
    assert {m.txn_id for m in after.ledger_matches} == {"GOLD-T1", "GOLD-T2"}
