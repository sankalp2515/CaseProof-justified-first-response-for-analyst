import json
from pathlib import Path

import pytest

from caseproof.config import Settings
from caseproof.pipeline.load import load_case
from caseproof.pipeline.orchestrator import Orchestrator


@pytest.mark.parametrize("provider", ["local", "gemini"])
def test_non_mock_loader_never_reads_renderer_transcripts(tmp_path, monkeypatch, provider):
    root = tmp_path / "kit"
    (root / "inputs").mkdir(parents=True)
    (root / "inputs/X.json").write_text(json.dumps({"case_id": "X", "initial_artifacts": []}))
    (root / "renderer_transcripts.json").write_text('{"forged": "INR 9999999"}')
    settings = Settings(
        _env_file=None,
        llm_provider=provider,
        llm_mode="live",
        gemini_api_key="",
        data_dir=tmp_path,
        object_dir=tmp_path / "objects",
        sqlite_url="sqlite:///" + str(tmp_path / "db"),
    )
    orchestrator = Orchestrator(settings)
    original = Path.read_text

    def guarded(path, *args, **kwargs):
        assert path.name != "renderer_transcripts.json", "strict runtime read a fixture transcript"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    load_case(orchestrator, root, "X")
    assert not orchestrator.fixtures
