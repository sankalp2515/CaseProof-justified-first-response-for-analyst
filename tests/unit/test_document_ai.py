import base64
from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image

from caseproof.config import Settings
from caseproof.domain.contracts import ArtifactRef


def fixture(tmp_path):
    data = BytesIO()
    Image.new("RGB", (100, 100), "white").save(data, format="PNG")
    raw = data.getvalue()
    artifact = ArtifactRef(
        artifact_id="A",
        case_id="C",
        kind="receipt",
        mime_type="image/png",
        sha256=sha256(raw).hexdigest(),
        byte_count=len(raw),
        object_key="unused",
    )
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        google_cloud_project="caseproof-test",
        documentai_location="asia-south1",
        documentai_processor_id="abc123",
        documentai_processor_version="pretrained-ocr-test",
        ocr_provider="documentai",
    )
    body = {
        "document": {
            "text": "INR 100\n",
            "pages": [
                {
                    "pageNumber": 1,
                    "lines": [
                        {
                            "layout": {
                                "confidence": 0.99,
                                "textAnchor": {"textSegments": [{"endIndex": "8"}]},
                                "boundingPoly": {
                                    "normalizedVertices": [
                                        {"x": 0.1, "y": 0.2},
                                        {"x": 0.8, "y": 0.2},
                                        {"x": 0.8, "y": 0.3},
                                        {"x": 0.1, "y": 0.3},
                                    ]
                                },
                            }
                        }
                    ],
                }
            ],
        }
    }
    return settings, artifact, raw, body


class Service:
    def __init__(self, body):
        self.body, self.calls = body, []

    def post(self, url, **kwargs):
        import httpx

        self.calls.append((url, kwargs))
        return httpx.Response(200, json=self.body, request=httpx.Request("POST", url))


def test_document_ai_reads_pixels_with_versioned_lines_and_normalized_boxes(tmp_path):
    from caseproof.adapters.document_ai import DocumentAI

    s, artifact, raw, body = fixture(tmp_path)
    service = Service(body)
    segments, run = DocumentAI(s, session=service).transcribe_image("C", artifact, raw)
    assert segments[0].text == "INR 100" and segments[0].box_2d == [200, 100, 300, 800]
    assert run.provider == "documentai" and run.mode == "live"
    assert "processorVersions/pretrained-ocr-test:process" in service.calls[0][0]
    assert base64.b64decode(service.calls[0][1]["json"]["rawDocument"]["content"]) == raw
    assert service.calls[0][1]["timeout"] == 45
    assert run.input_digest == artifact.sha256


@pytest.mark.parametrize("mutation", ["box", "page", "anchor", "confidence", "digest"])
def test_document_ai_rejects_invalid_provider_output_or_changed_evidence(tmp_path, mutation):
    from caseproof.adapters.document_ai import DocumentAI
    from caseproof.adapters.provider import ProviderError

    s, artifact, raw, body = fixture(tmp_path)
    layout = body["document"]["pages"][0]["lines"][0]["layout"]
    if mutation == "box":
        layout["boundingPoly"]["normalizedVertices"][0]["x"] = 2
    elif mutation == "page":
        body["document"]["pages"].append(body["document"]["pages"][0])
    elif mutation == "anchor":
        layout["textAnchor"]["textSegments"][0]["endIndex"] = "1000"
    elif mutation == "confidence":
        layout["confidence"] = float("nan")
    else:
        artifact.sha256 = "0" * 64
    with pytest.raises(ProviderError, match="DOCUMENT_AI_ERROR"):
        DocumentAI(s, session=Service(body)).transcribe_image("C", artifact, raw)


def test_document_ai_low_confidence_is_explicit_and_blank_page_is_valid(tmp_path):
    from caseproof.adapters.document_ai import DocumentAI

    s, artifact, raw, body = fixture(tmp_path)
    body["document"]["pages"][0]["lines"][0]["layout"]["confidence"] = 0.3
    segments, _ = DocumentAI(s, session=Service(body)).transcribe_image("C", artifact, raw)
    assert segments[0].ocr_model_id.endswith(":low-confidence")
    body["document"]["pages"][0]["lines"] = []
    assert DocumentAI(s, session=Service(body)).transcribe_image("C", artifact, raw)[0] == []


@pytest.mark.parametrize(
    "version, valid",
    [
        ("pretrained-ocr-v1.0-2020-09-23", True),  # real Google stable version ID
        ("pretrained-ocr-v2.1.1-2025-01-31", True),
        ("../other-processor", False),
        ("v1/../../x", False),
        ("v1..2", False),
    ],
)
def test_processor_version_accepts_real_dotted_ids_only(tmp_path, version, valid):
    from caseproof.adapters.document_ai import DocumentAI

    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        google_cloud_project="caseproof-test",
        documentai_location="asia-south1",
        documentai_processor_id="abc123",
        documentai_processor_version=version,
        ocr_provider="documentai",
    )
    if valid:
        assert DocumentAI(settings, session=object()).resource.endswith("/" + version)
    else:
        with pytest.raises(ValueError):
            DocumentAI(settings, session=object())
