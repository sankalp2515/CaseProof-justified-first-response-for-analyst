from caseproof.adapters.sqlite_casestore import ConflictError


def run_one(jobs, orchestrator):
    job = jobs.take()
    if not job:
        return None
    try:
        if orchestrator.store.get(job["case_id"]).revision != job["revision"]:
            jobs.finish(job["job_id"], "stale", lease_token=job["lease_token"])
            return job["job_id"]
        with jobs.lease(job):
            orchestrator.process(job["case_id"], expected_revision=job["revision"])
        jobs.finish(job["job_id"], "done", lease_token=job["lease_token"])
    except ConflictError:
        jobs.finish(job["job_id"], "stale", lease_token=job["lease_token"])
    except Exception as e:
        jobs.finish(
            job["job_id"],
            "failed",
            str(e) if str(e) in {"LLM_PROVIDER_ERROR", "LOCAL_OCR_ERROR"} else type(e).__name__,
            lease_token=job["lease_token"],
        )
    return job["job_id"]
