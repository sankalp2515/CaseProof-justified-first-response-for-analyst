"""Explicit offline understanding: real Tesseract pixels plus literal extraction rules."""

import time

import httpx

from caseproof.domain.contracts import RunMeta, Segment, hash_json


class LocalLLM:
    model_id = "local-literal-rules-v2"

    def __init__(self, settings):
        self.settings = settings

    def transcribe_image(self, case_id, artifact, data):
        from caseproof.adapters.provider import ProviderError

        start = time.perf_counter()
        try:
            response = httpx.post(
                self.settings.local_ocr_url + "/v1/transcribe",
                content=data,
                headers={"Content-Type": artifact.mime_type},
                timeout=45,
                trust_env=False,
            )
            response.raise_for_status()
            result = response.json()
            segments = [
                Segment(
                    segment_id=f"seg-{artifact.artifact_id}-{i}",
                    artifact_id=artifact.artifact_id,
                    text=line["text"],
                    box_2d=line["box_2d"],
                    source="model_ocr",
                    ocr_model_id=result["model_id"]
                    + (":uncertain-timestamp" if line.get("uncertain_timestamp") else ""),
                )
                for i, line in enumerate(result["lines"])
            ]
        except Exception:
            raise ProviderError("LOCAL_OCR_ERROR") from None
        return segments, RunMeta(
            mode="local",
            provider="tesseract",
            model_id=result["model_id"],
            input_digest=artifact.sha256,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def extract_claims(self, case_id, revision, segments):
        from caseproof.adapters.literal_extractor import LiteralExtractor

        start = time.perf_counter()
        result = LiteralExtractor().extract_claims(case_id, revision, segments)
        result.run = RunMeta(
            mode="local",
            provider="local-rules",
            model_id=self.model_id,
            input_digest=hash_json([s.model_dump() for s in segments]),
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        return result
