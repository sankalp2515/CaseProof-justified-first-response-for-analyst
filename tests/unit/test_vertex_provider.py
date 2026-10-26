"""Vertex routing and trust-boundary tests; no credentials or network calls."""

import json
from types import SimpleNamespace

import pytest

from caseproof.adapters import gemini_llm
from caseproof.adapters.provider import Provider, ProviderError
from caseproof.config import Settings
from caseproof.domain.contracts import ArtifactRef


def settings(tmp_path, **overrides):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        llm_provider="vertex",
        llm_mode="live",
        gemini_api_key="unused-developer-key",
        gemini_model="gemini-3.1-flash-lite",
        google_cloud_project="caseproof-test",
        google_cloud_location="global",
        **overrides,
    )


def test_vertex_client_uses_project_identity_not_developer_api_key(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(gemini_llm.genai, "Client", lambda **kw: captured.update(kw))
    gemini_llm.client(settings(tmp_path))
    assert captured["vertexai"] is True
    assert captured["project"] == "caseproof-test" and captured["location"] == "global"
    assert "api_key" not in captured
    assert captured["http_options"].api_version == "v1"


@pytest.mark.parametrize("field", ["google_cloud_project", "google_cloud_location"])
def test_vertex_requires_explicit_usable_project_and_location(tmp_path, monkeypatch, field):
    s = settings(tmp_path)
    setattr(s, field, "")
    monkeypatch.setattr(gemini_llm.genai, "Client", lambda **kw: pytest.fail("SDK called"))
    with pytest.raises(ValueError):
        gemini_llm.client(s)


def test_vertex_requires_pinned_model_even_when_developer_choice_is_cached(tmp_path):
    s = settings(tmp_path)
    s.gemini_model = ""
    (tmp_path / "model_choice.json").write_text(json.dumps({"model": "unrelated-model"}))
    with pytest.raises(ValueError):
        gemini_llm.select_model(s)


def test_vertex_transcription_keeps_citation_boxes_and_provider_metadata(tmp_path, monkeypatch):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            text=json.dumps({"lines": [{"text": "INR 500", "box_2d": [10, 20, 80, 400]}]}),
            usage_metadata=SimpleNamespace(prompt_token_count=40, candidates_token_count=12),
        )

    monkeypatch.setattr(
        gemini_llm.genai,
        "Client",
        lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )
    s = settings(tmp_path)
    provider = Provider(s)
    artifact = ArtifactRef(
        artifact_id="A",
        case_id="C",
        kind="receipt",
        mime_type="image/png",
        sha256="synthetic",
        byte_count=3,
        object_key="evidence",
    )
    segments, run = provider.transcribe_image("C", artifact, b"png")
    assert segments[0].box_2d == [10, 20, 80, 400]
    assert run.provider == "vertex" and run.mode == "live" and run.tokens_in == 40
    assert len(calls) == 1
    _, run = provider.transcribe_image("C", artifact, b"png")
    assert run.mode == "cache" and len(calls) == 1
    s.google_cloud_project = "another-project"
    Provider(s).transcribe_image("C2", artifact, b"png")
    assert len(calls) == 2, "A different Vertex project must not reuse cached provenance"


def test_vertex_configuration_failure_does_not_silently_use_local_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gemini_llm.genai,
        "Client",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("credential lookup failed")),
    )
    provider = Provider(settings(tmp_path))
    with pytest.raises(ProviderError, match="LLM_PROVIDER_ERROR"):
        provider.extract_claims("C", 1, [])


def test_vertex_tool_proposals_are_live_scoped_and_project_isolated(tmp_path, monkeypatch):
    from caseproof.adapters.investigation_tools import propose

    called = []

    def generate(**kwargs):
        called.append(kwargs)
        parts = [
            SimpleNamespace(function_call=SimpleNamespace(name="lookup_transactions", args=a))
            for a in ({"account": "C1"}, {"account": "UNRELATED"})
        ]
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))], usage_metadata=None
        )

    monkeypatch.setattr(
        gemini_llm.genai,
        "Client",
        lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )
    s = settings(tmp_path)
    scope = {"account": "C1", "payees": []}
    calls, run = propose(Provider(s), "C", scope)
    assert calls == [{"name": "lookup_transactions", "args": {"account": "C1"}}]
    assert run.provider == "vertex" and run.mode == "live"
    s.google_cloud_location = "us-central1"
    propose(Provider(s), "C2", scope)
    assert len(called) == 2


def test_vertex_circuit_does_not_block_a_different_project(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(gemini_llm.genai, "Client", lambda **kw: object())
    s = settings(tmp_path)
    (tmp_path / "provider_unavailable.json").write_text(
        json.dumps(
            {
                "provider": "vertex",
                "model_id": s.gemini_model,
                "status_code": 403,
                "project": "another-project",
                "location": "global",
                "day": datetime.now(timezone.utc).date().isoformat(),
            }
        )
    )
    assert not Provider(s).circuit()


def test_vertex_smoke_check_has_project_specific_cache_and_provider(tmp_path, monkeypatch):
    called = []

    def generate(**kwargs):
        called.append(kwargs)
        return SimpleNamespace(text='{"ok": true}', usage_metadata=None)

    monkeypatch.setattr(
        gemini_llm.genai,
        "Client",
        lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )
    s = settings(tmp_path)
    assert json.loads(gemini_llm.smoke_check(s))["provider"] == "vertex"
    s.google_cloud_project = "another-project"
    assert json.loads(gemini_llm.smoke_check(s))["mode"] == "live"
    assert len(called) == 2


def test_extraction_cites_short_aliases_and_maps_them_to_real_segment_ids(tmp_path, monkeypatch):
    from caseproof.domain.contracts import Segment

    sent = []

    def generate(**kwargs):
        sent.append(json.loads(kwargs["contents"][1]))
        claim = {
            "claim_id": "x",
            "kind": "amount",
            "normalized_value": 50000,
            "anchor_segment_ids": ["S2"],
        }
        bad = {**claim, "kind": "currency", "anchor_segment_ids": ["seg-ART-0"]}
        return SimpleNamespace(
            text=json.dumps({"claims": [claim, bad], "unresolved_fields": []}),
            usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=1),
            candidates=[SimpleNamespace(finish_reason="STOP")],
        )

    monkeypatch.setattr(
        gemini_llm.genai,
        "Client",
        lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )
    segments = [
        Segment(segment_id=f"seg-ART-1066ea88ab1b-{i}", artifact_id="ART-1066ea88ab1b", text=t)
        for i, t in enumerate(["Paid to fraud@upi", "INR 500.00"])
    ]
    result = Provider(settings(tmp_path)).extract_claims("C", 1, segments)
    assert [s["segment_id"] for s in sent[0]["segments"]] == ["S1", "S2"]
    assert result.claims[0].anchor_segment_ids == ["seg-ART-1066ea88ab1b-1"]
    # An unmappable citation is passed through unchanged, so validation rejects it.
    assert result.claims[1].anchor_segment_ids == ["seg-ART-0"]
