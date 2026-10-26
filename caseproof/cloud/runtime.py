"""Cloud dependency composition. Never constructs a local case or bank database."""

from caseproof.adapters.bigquery_bank import BigQuery
from caseproof.adapters.cloud_bank_ingestion import CloudBankIngestion
from caseproof.adapters.cloud_service import CloudService
from caseproof.adapters.firestore_casestore import FirestoreCaseStore
from caseproof.adapters.firestore_documents import FirestoreDocuments
from caseproof.adapters.firestore_jobs import FirestoreJobs
from caseproof.adapters.firestore_llm_cache import FirestoreLLMCache
from caseproof.adapters.gcs_storage import GCSStorage
from caseproof.adapters.provider import Provider
from caseproof.adapters.quarantine_storage import EvidenceNotReady, QuarantineStorage
from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.pipeline.ingest import Intake


def configure(o):
    s = o.s
    docs = FirestoreDocuments(s.google_cloud_project, s.firestore_namespace)
    o.store = FirestoreCaseStore(docs, s.cloud_max_cases)
    o.jobs = FirestoreJobs(o.store, s.job_lease_seconds)
    o.bigquery = BigQuery(
        s.google_cloud_project,
        s.bigquery_dataset,
        s.google_cloud_location,
        maximum_bytes=s.bigquery_maximum_bytes,
    )
    o.bank_ingestion = CloudBankIngestion(o.store, o.bigquery)
    o.storage = QuarantineStorage(
        GCSStorage(s.gcs_quarantine_bucket),
        GCSStorage(s.gcs_bucket),
        docs,
        CloudService(s.cloud_scanner_url, timeout=150),
    )
    o.intake = Intake(o.storage, o.store)
    o.llm = Provider(s, cache=FirestoreLLMCache(s, docs))
    o.fixtures = {}


# Matches the Cloud Tasks queue retry budget (infra/google/runtime/main.tf). Wide
# enough to outlast transient Vertex 429 capacity limits and the provider circuit.
MAX_JOB_ATTEMPTS = 6


def process_job(o, jid):
    job = o.jobs.claim(jid)
    if job is None:
        return {"acknowledged": True, "duplicate_or_stale": True}
    import time

    from caseproof.cloud.observability import emit

    emit(
        "job_attempt",
        job_id=jid,
        attempt=job["attempt_count"],
        queue_age_ms=round(max(0, time.time() - job["enqueued_at"]) * 1000, 2),
    )
    try:
        with o.jobs.lease(job), o.store.worker_fence(job):
            o.process(job["case_id"], expected_revision=job["revision"])
        o.jobs.finish(jid, "done", lease_token=job["lease_token"])
        return {"acknowledged": True}
    except ConflictError as error:
        if str(error) == "job_lease_lost":
            raise
        if str(error) == "approved_delivery_in_progress_retry":
            o.jobs.defer(job, "DELIVERY_IN_PROGRESS")
            raise
        o.jobs.finish(jid, "stale", lease_token=job["lease_token"])
        return {"acknowledged": True, "stale": True}
    except EvidenceNotReady:
        o.jobs.defer(job, "EVIDENCE_SCAN_PENDING_OR_REJECTED")
        raise
    except Exception:
        if job["attempt_count"] < MAX_JOB_ATTEMPTS:
            o.jobs.defer(job, "CLOUD_PROCESSING_RETRY")
        else:
            o.jobs.finish(jid, "failed", "CLOUD_PROCESSING_FAILED", job["lease_token"])
        raise
