from pathlib import Path

from caseproof.config import Settings
from caseproof.domain.contracts import Actor, CaseSnapshot


def test_contracts_roundtrip():
    s = CaseSnapshot(case_id="T", revision=1)
    assert CaseSnapshot.model_validate_json(s.model_dump_json()) == s
    assert Actor(user_id="demo", role="analyst", tenant_id="demo").role == "analyst"


def test_env_missing_key_runs_mock_mode():
    s = Settings(_env_file=None, gemini_api_key="", groq_api_key="", nvidia_api_key="")
    assert s.effective_mode == "live"  # V2: missing keys cannot silently downgrade live.


def test_no_gold_paths_in_app():
    for p in Path("caseproof").rglob("*.py"):
        assert "private_gold" not in p.read_text() and "case_index.csv" not in p.read_text()
