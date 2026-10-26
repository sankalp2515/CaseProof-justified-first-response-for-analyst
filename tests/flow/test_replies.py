from caseproof.config import Settings
from caseproof.domain.evidence import diff
from caseproof.pipeline.load import load_case
from caseproof.pipeline.orchestrator import Orchestrator
from kitgen.generate import generate
from mock_services.customer import reply


def test_reply_creates_new_revision_and_diff(tmp_path):
    root = tmp_path / "kit"
    bank = str(tmp_path / "bank.duckdb")
    generate(root, bank, count=1)
    s = Settings(
        _env_file=None,
        llm_mode="mock",
        data_dir=tmp_path,
        object_dir=tmp_path / "objects",
        sqlite_url="sqlite:///" + str(tmp_path / "db.sqlite"),
        duckdb_path=bank,
    )
    o = Orchestrator(s)
    load_case(o, root, "GOLD-001")
    initial = o.process("GOLD-001")
    assert initial.readiness.disposition == "REVIEW_REQUIRED"
    assert initial.requests[0].catalogue_id == "confirm_additional_transfer"
    after = reply(o, root, "GOLD-001", initial.requests[0].request_id)
    assert after.revision > initial.revision
    assert after.readiness.disposition == "COMPLETE_CANDIDATE"
    assert len(after.linked) == 8
    assert diff(initial, after)["added"]
