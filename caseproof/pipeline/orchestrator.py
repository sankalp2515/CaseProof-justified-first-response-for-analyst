from typing import Any

from caseproof.adapters.provider import Provider
from caseproof.adapters.sqlite_casestore import CaseStore, ConflictError
from caseproof.adapters.sqlite_jobs import SQLiteJobs
from caseproof.adapters.storage import build_storage
from caseproof.domain.contracts import hash_json
from caseproof.domain.validator import validate_claims
from caseproof.pipeline.ingest import Intake
from caseproof.pipeline.transcribe import segment_text


class Orchestrator:
    def __init__(self, settings):
        self.s = settings
        if settings.runtime_backend == "google":
            from caseproof.cloud.runtime import configure

            configure(self)
            return
        self.store = CaseStore(settings.sqlite_url)
        from caseproof.domain.ownership import initialise

        initialise(self.store)
        self.storage = build_storage(settings)
        self.intake = Intake(self.storage, self.store)
        self.jobs = SQLiteJobs(self.store)
        self.jobs.lease_seconds = settings.job_lease_seconds
        self.llm = Provider(settings)
        self.fixtures = {}

    def process(self, case_id: str, expected_revision: Any = None, investigate: Any = True) -> Any:
        """Transcribe, extract, validate, investigate, and publish a new case revision."""
        snap = self.store.get(case_id)
        old = snap.revision
        if expected_revision is not None and expected_revision != old:
            raise ConflictError("stale_revision")
        segs = []
        runs = list(snap.run_meta)
        for a in snap.artifacts:
            existing = [s for s in snap.segments if s.artifact_id == a.artifact_id]
            if existing:
                segs.extend(existing)
                continue
            data = self.storage.read(a.object_key)
            if a.mime_type == "text/plain":
                segs.extend(segment_text(a, data))
            else:
                ss, run = self.llm.transcribe_image(case_id, a, data, self.fixtures.get(a.sha256))
                segs.extend(ss)
                runs.append(run)
        result = self.llm.extract_claims(case_id, old, segs)
        for c in result.claims:
            c.claim_id = (
                "cl-"
                + hash_json(
                    {"kind": c.kind, "value": c.normalized_value, "anchors": c.anchor_segment_ids}
                )[:16]
            )
        # One corrective attempt. Never publish invalid anchors.
        try:
            claims = validate_claims(result.claims, segs)
        except ValueError:
            result = self.llm.extract_claims(
                case_id,
                old,
                segs,
                corrective_action="Repair unknown citation IDs; cite only supplied segments",
            )
            for c in result.claims:
                c.claim_id = (
                    "cl-"
                    + hash_json(
                        {
                            "kind": c.kind,
                            "value": c.normalized_value,
                            "anchors": c.anchor_segment_ids,
                        }
                    )[:16]
                )
            claims = validate_claims(result.claims, segs)
        from caseproof.pipeline.extract import preserve_text_observations

        claims = preserve_text_observations(claims, segs)
        for c in claims:
            c.claim_id = (
                "cl-"
                + hash_json(
                    {"kind": c.kind, "value": c.normalized_value, "anchors": c.anchor_segment_ids}
                )[:16]
            )
        segment_map = {s.segment_id: s for s in segs}
        artifact_map = {a.artifact_id: a for a in snap.artifacts}
        for claim in claims:
            if any(
                (segment_map[a].ocr_model_id or "").endswith(":low-confidence")
                for a in claim.anchor_segment_ids
            ):
                claim.evidence_state = "reported"
                claim.confidence_note = "Low-confidence Document AI observation; verify original image."
            if claim.kind == "txn_datetime" and all(
                artifact_map[segment_map[a].artifact_id].kind == "call_log"
                for a in claim.anchor_segment_ids
            ):
                claim.evidence_state = "unresolved"
                claim.confidence_note = "Call time is not debit time"
        snap.segments = segs
        snap.claims = claims
        snap.run_meta = runs + [result.run]
        if snap.corrections:
            from caseproof.domain.evidence import apply_corrections

            snap.claims = apply_corrections(snap.claims, snap.corrections, segs)
        from caseproof.pipeline.investigate import assess

        assess(self, snap, investigate)
        from caseproof.domain.facts import merge_facts

        snap.facts = merge_facts(snap.claims)
        snap.revision += 1
        return self.store.publish(snap, old, "processed")
