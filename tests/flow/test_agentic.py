from caseproof.config import Settings
from caseproof.pipeline.load import load_case
from caseproof.pipeline.orchestrator import Orchestrator
from kitgen.generate import generate


def test_agentic_flag_preserves_authoritative_facts(tmp_path):
    root = tmp_path / "kit"
    bank = str(tmp_path / "bank.duckdb")
    generate(root, bank, count=1)
    s = Settings(
        _env_file=None,
        llm_mode="mock",
        data_dir=tmp_path,
        object_dir=tmp_path / "objects",
        sqlite_url="sqlite:///" + str(tmp_path / "cases.sqlite"),
        duckdb_path=bank,
    )
    from datetime import datetime

    replay = datetime.fromisoformat("2026-10-01T12:08:00+05:30")
    a = Orchestrator(s)
    a.clock_as_of = replay
    load_case(a, root, "GOLD-001", "plain")
    plain = a.process("plain")
    s.agentic_investigate = True
    b = Orchestrator(s)
    b.clock_as_of = replay
    load_case(b, root, "GOLD-001", "flagged")
    flagged = b.process("flagged")
    for field in ["ledger_matches", "unreported", "linked", "gaps", "readiness"]:
        assert getattr(plain, field) == getattr(flagged, field)
    assert any(r.model_id == "mock-tool-proposal-v1" for r in flagged.run_meta)
