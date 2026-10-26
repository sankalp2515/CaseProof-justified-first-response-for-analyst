import httpx
import pytest

from caseproof.adapters.local_llm import LocalLLM
from caseproof.adapters.provider import ProviderError
from caseproof.config import Settings
from caseproof.domain.contracts import ArtifactRef


def test_local_ocr_uses_http_pixels_not_renderer(monkeypatch):
    artifact = ArtifactRef(
        artifact_id="A",
        case_id="C",
        kind="receipt",
        mime_type="image/png",
        sha256="a" * 64,
        byte_count=6,
        object_key="aa/" + "a" * 64,
    )

    def post(url, **kwargs):
        assert kwargs["content"] == b"pixels"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "lines": [{"text": "INR 100", "box_2d": [0, 0, 100, 500]}],
                "model_id": "real-local-ocr",
            },
        )

    monkeypatch.setattr(httpx, "post", post)
    segments, meta = LocalLLM(Settings(_env_file=None)).transcribe_image("C", artifact, b"pixels")
    assert segments[0].text == "INR 100" and meta.mode == "local"
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("offline"))
    )
    with pytest.raises(ProviderError, match="LOCAL_OCR_ERROR"):
        LocalLLM(Settings(_env_file=None)).transcribe_image("C", artifact, b"pixels")
