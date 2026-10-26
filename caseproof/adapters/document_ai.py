"""Document AI OCR with original text anchors, bounded requests and explicit failures."""

import base64
import math
import re
import time

from caseproof.adapters.google_http import authorized_session
from caseproof.adapters.object_validation import validate_evidence
from caseproof.domain.contracts import RunMeta, Segment


class DocumentAI:
    def __init__(self, settings, *, session=None):
        self.s = settings
        components = [
            settings.google_cloud_project,
            settings.documentai_location,
            settings.documentai_processor_id,
            settings.documentai_processor_version,
        ]
        # Real version IDs contain dots (pretrained-ocr-v1.0-2020-09-23); no "/" or "..".
        if not all(
            re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", part or "") for part in components
        ):
            raise ValueError(
                "Document AI requires explicit project, location, processor and version"
            )
        project, location, processor, version = components
        self.resource = (
            f"projects/{project}/locations/{location}/processors/{processor}"
            f"/processorVersions/{version}"
        )
        self.url = f"https://{location}-documentai.googleapis.com/v1/{self.resource}:process"
        self.session = session if session is not None else authorized_session()

    def transcribe_image(self, case_id, artifact, data):
        from caseproof.adapters.provider import ProviderError

        started = time.perf_counter()
        try:
            if case_id != artifact.case_id or artifact.mime_type not in {"image/png", "image/jpeg"}:
                raise ValueError("image evidence required")
            _, digest = validate_evidence(data, artifact.mime_type)
            if digest != artifact.sha256 or len(data) != artifact.byte_count:
                raise ValueError("changed evidence")
            response = self.session.post(
                self.url,
                json={
                    "rawDocument": {
                        "content": base64.b64encode(data).decode("ascii"),
                        "mimeType": artifact.mime_type,
                    }
                },
                timeout=45,
            )
            response.raise_for_status()
            document = response.json()["document"]
            text, pages = document.get("text", ""), document["pages"]
            if not isinstance(text, str) or len(text) > 200_000 or len(pages) != 1:
                raise ValueError("invalid image OCR document")
            page = pages[0]
            if page.get("pageNumber", 1) != 1 or len(page.get("lines", [])) > 2000:
                raise ValueError("invalid page")
            segments = []
            for index, line in enumerate(page.get("lines", [])):
                layout = line["layout"]
                confidence = layout.get("confidence", 0)
                if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    raise ValueError("invalid confidence")
                parts = []
                for anchor in layout["textAnchor"]["textSegments"]:
                    start, end = int(anchor.get("startIndex", 0)), int(anchor["endIndex"])
                    if not 0 <= start < end <= len(text):
                        raise ValueError("invalid text anchor")
                    parts.append(text[start:end])
                content = "".join(parts).strip()
                if not content:
                    continue
                vertices = layout["boundingPoly"]["normalizedVertices"]
                if len(vertices) < 3:
                    raise ValueError("missing source polygon")
                xs, ys = [p.get("x", 0) for p in vertices], [p.get("y", 0) for p in vertices]
                if any(not math.isfinite(v) or not 0 <= v <= 1 for v in xs + ys):
                    raise ValueError("invalid source polygon")
                model = self.resource + (
                    ":low-confidence" if confidence < self.s.documentai_min_confidence else ""
                )
                segments.append(
                    Segment(
                        segment_id=f"seg-{artifact.artifact_id}-{index}",
                        artifact_id=artifact.artifact_id,
                        text=content,
                        source="model_ocr",
                        ocr_model_id=model,
                        box_2d=[
                            round(min(ys) * 1000),
                            round(min(xs) * 1000),
                            round(max(ys) * 1000),
                            round(max(xs) * 1000),
                        ],
                    )
                )
        except Exception:
            raise ProviderError("DOCUMENT_AI_ERROR") from None
        return segments, RunMeta(
            mode="live",
            provider="documentai",
            model_id=self.resource,
            input_digest=artifact.sha256,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
