import json
from pathlib import Path

from google.genai import types

from caseproof.adapters.gemini_llm import client, select_model
from caseproof.adapters.llm_cache import CacheMiss, CallCapError, LLMCache
from caseproof.adapters.mock_llm import MockLLM
from caseproof.domain.contracts import CandidateClaim, ExtractionResult, RunMeta, Segment, hash_json

TRANSCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "box_2d": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["text", "box_2d"],
            },
        }
    },
    "required": ["lines"],
}
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": CandidateClaim.model_json_schema()},
        "unresolved_fields": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["claims", "unresolved_fields"],
}


class ProviderError(RuntimeError):
    """Safe provider failure; never contains evidence or credential detail."""


class Provider:
    def __init__(self, settings, cache=None):
        self.init_error = False
        self.s = settings
        self.mock = MockLLM()
        self.cache = cache if cache is not None else LLMCache(settings)
        self.provider = settings.llm_provider
        self.mode = settings.effective_mode
        self.model_id = "rules-v1"
        self.c = None
        self.compat = None
        if self.provider == "local":
            from caseproof.adapters.local_llm import LocalLLM

            self.local = LocalLLM(settings)
            self.model_id = self.local.model_id
            return
        if self.mode != "mock":
            try:
                if self.provider in ("gemini", "vertex"):
                    self.model_id = select_model(settings)
                    self.c = client(settings)
                else:
                    from caseproof.adapters.openai_compat_llm import OpenAICompat

                    self.compat = OpenAICompat(settings)
                    self.model_id = self.compat.model_id
            except Exception:
                if settings.allow_fallback:
                    self.mode = "mock"
                else:
                    self.init_error = True

    def circuit(self):
        p = self.s.data_dir / "provider_unavailable.json"
        if not p.exists():
            return False
        from datetime import datetime, timezone

        r = json.loads(p.read_text())
        if self.provider == "vertex" and (
            r.get("project") != self.s.google_cloud_project
            or r.get("location") != self.s.google_cloud_location
        ):
            return False
        if r.get("resolved_at"):
            return False
        if r.get("retry_at") and datetime.fromisoformat(r["retry_at"]) <= datetime.now(
            timezone.utc
        ):
            return False
        return (
            r.get("provider") == self.provider
            and r.get("day") == datetime.now(timezone.utc).date().isoformat()
            and (r.get("status_code") in (401, 403, 429) or r.get("model_id") == self.model_id)
        )

    def cache_inputs(self, inputs):
        if self.provider == "vertex":
            return {
                **inputs,
                "vertex_context": {
                    "project": self.s.google_cloud_project,
                    "location": self.s.google_cloud_location,
                },
            }
        return inputs

    def generate(self, case_id, task, inputs, schema, image=None, mime=None):
        if len(json.dumps(inputs, ensure_ascii=False)) > self.s.llm_max_input_chars:
            raise CallCapError("LLM input size limit reached")
        prompt = (
            Path(__file__).resolve().parents[1]
            / "prompts"
            / (task + ("-v2.md" if task == "extract" else "-v1.md"))
        ).read_text(encoding="utf-8")
        inputs = {**inputs, "schema_digest": hash_json(schema)}
        cache_inputs = self.cache_inputs(inputs)
        hit = self.cache.peek(self.provider, self.model_id, prompt, cache_inputs)
        if hit:
            return hit
        if self.circuit():
            raise RuntimeError("provider circuit open")

        def call():
            if self.init_error:
                raise ProviderError("LLM_PROVIDER_ERROR")
            if self.compat:
                return self.compat.generate(prompt, inputs, schema, image, mime)
            content = [prompt, json.dumps(inputs, ensure_ascii=False)]
            if image:
                content.append(types.Part.from_bytes(data=image, mime_type=mime))
            r = self.c.models.generate_content(
                model=self.model_id,
                contents=content,
                config=types.GenerateContentConfig(
                    automatic_continuation=False,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    response_mime_type="application/json",
                    response_json_schema=schema,
                    temperature=0,
                    max_output_tokens=self.s.llm_max_output_tokens,
                    # Schema-bound extraction needs no reasoning budget; thinking tokens
                    # otherwise share max_output_tokens and truncate the JSON.
                    # Gemini 3+ replaced the token budget with a thinking level.
                    thinking_config=types.ThinkingConfig(thinking_level="MINIMAL")
                    if not self.model_id.startswith("gemini-2")
                    else types.ThinkingConfig(thinking_budget=0),
                ),
            )
            reason = getattr(getattr(r, "candidates", [None])[0], "finish_reason", None)
            if str(getattr(reason, "name", reason) or "").upper() == "MAX_TOKENS":
                raise ProviderError("LLM_OUTPUT_TRUNCATED")
            return json.loads(r.text), r.usage_metadata

        try:
            return self.cache.call(
                case_id, self.provider, self.model_id, prompt, cache_inputs, call
            )
        except Exception as e:
            code = getattr(e, "code", None)
            if code in (401, 403, 404, 429) or (
                self.provider in ("gemini", "vertex") and code == 503
            ):
                from datetime import datetime, timedelta, timezone

                self.s.data_dir.mkdir(parents=True, exist_ok=True)
                (self.s.data_dir / "provider_unavailable.json").write_text(
                    json.dumps(
                        {
                            "provider": self.provider,
                            "project": self.s.google_cloud_project,
                            "location": self.s.google_cloud_location,
                            "model_id": self.model_id,
                            "status_code": code,
                            "day": datetime.now(timezone.utc).date().isoformat(),
                            "retry_at": (
                                datetime.now(timezone.utc)
                                + timedelta(
                                    # Shared-capacity 429s clear quickly; retry soon.
                                    seconds=60 if code in (429, 503) else 86400
                                )
                            ).isoformat(),
                        }
                    )
                )
            raise

    def transcribe_image(self, case_id, artifact, data, fixture=None):
        if self.s.ocr_provider == "documentai":
            if self.provider != "vertex" or self.mode != "live" or self.s.allow_fallback:
                raise ProviderError(
                    "Document AI requires explicit live Vertex mode without fallback"
                )
            from caseproof.adapters.document_ai import DocumentAI
            from caseproof.adapters.object_validation import validate_evidence

            try:
                _, digest = validate_evidence(data, artifact.mime_type)
                if (
                    digest != artifact.sha256
                    or len(data) != artifact.byte_count
                    or case_id != artifact.case_id
                ):
                    raise ValueError("changed evidence")
            except ValueError:
                raise ProviderError("DOCUMENT_AI_ERROR") from None

            processor = "/".join(
                (
                    self.s.google_cloud_project,
                    self.s.documentai_location,
                    self.s.documentai_processor_id,
                    self.s.documentai_processor_version,
                )
            )

            def transcribe():
                segments, _ = DocumentAI(self.s).transcribe_image(case_id, artifact, data)
                return {
                    "lines": [
                        s.model_dump(mode="json", exclude={"segment_id", "artifact_id"})
                        for s in segments
                    ]
                }, None

            result = self.cache.call(
                case_id,
                "documentai",
                processor,
                "document-ai-lines-v1",
                {"sha256": artifact.sha256, "threshold": self.s.documentai_min_confidence},
                transcribe,
            )
            return [
                Segment(
                    segment_id=f"seg-{artifact.artifact_id}-{index}",
                    artifact_id=artifact.artifact_id,
                    **line,
                )
                for index, line in enumerate(result["data"]["lines"])
            ], RunMeta(**result["run"])
        if self.provider == "local":
            return self.local.transcribe_image(case_id, artifact, data)
        if self.mode == "mock":
            return self.mock.transcribe_image(case_id, artifact, data, fixture)
        try:
            r = self.generate(
                case_id,
                "transcribe",
                {"sha256": artifact.sha256},
                TRANSCRIPT_SCHEMA,
                data,
                artifact.mime_type,
            )
            segs = [
                Segment(
                    segment_id=f"seg-{artifact.artifact_id}-{i}",
                    artifact_id=artifact.artifact_id,
                    text=x["text"],
                    box_2d=x.get("box_2d") if self.provider in ("gemini", "vertex") else None,
                    source="model_ocr",
                    ocr_model_id=self.model_id,
                )
                for i, x in enumerate(r["data"]["lines"])
            ]
            return segs, RunMeta(**r["run"])
        except (CacheMiss, CallCapError):
            raise
        except Exception:
            if not self.s.allow_fallback:
                raise ProviderError("LLM_PROVIDER_ERROR") from None
            segs, run = self.mock.transcribe_image(case_id, artifact, data, fixture)
            run.model_id = "fallback:" + run.model_id
            return segs, run

    def extract_claims(self, case_id, revision, segments, corrective_action=None):
        if self.provider == "local":
            return self.local.extract_claims(case_id, revision, segments)
        if self.mode == "mock":
            return self.mock.extract_claims(case_id, revision, segments)
        # Models abbreviate long segment IDs (seg-ART-0 for seg-ART-1066ea88ab1b-0).
        # Cite short aliases instead and map them back here; anything unmappable
        # stays unknown and is still rejected by citation validation.
        aliases = {f"S{i + 1}": seg.segment_id for i, seg in enumerate(segments)}
        alias_of = {real: alias for alias, real in aliases.items()}
        try:
            r = self.generate(
                case_id,
                "extract",
                {
                    "segments": [
                        {**seg.model_dump(), "segment_id": alias_of[seg.segment_id]}
                        for seg in segments
                    ],
                    "corrective_action": corrective_action,
                },
                EXTRACT_SCHEMA,
            )
            claims = [
                {
                    **c,
                    "anchor_segment_ids": [
                        aliases.get(anchor, anchor) for anchor in c.get("anchor_segment_ids", [])
                    ],
                }
                for c in r["data"]["claims"]
            ]
            return ExtractionResult(
                case_id=case_id,
                source_revision=revision,
                claims=[CandidateClaim(**c) for c in claims],
                unresolved_fields=r["data"]["unresolved_fields"],
                run=RunMeta(**r["run"]),
            )
        except (CacheMiss, CallCapError):
            raise
        except Exception:
            if not self.s.allow_fallback:
                raise ProviderError("LLM_PROVIDER_ERROR") from None
            result = self.mock.extract_claims(case_id, revision, segments)
            result.run.model_id = "fallback:rules-v1"
            return result

    def explain(self, *args):
        return self.mock.explain(*args)

    def summarise(self, *args):
        return self.mock.summarise(*args)
