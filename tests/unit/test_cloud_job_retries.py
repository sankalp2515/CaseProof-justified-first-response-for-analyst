from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from caseproof.cloud.runtime import MAX_JOB_ATTEMPTS, process_job


def runtime(attempt):
    calls = []
    job = {
        "job_id": "J",
        "case_id": "C",
        "revision": 3,
        "attempt_count": attempt,
        "enqueued_at": 0,
        "lease_token": "T",
    }

    def unavailable(*args, **kwargs):
        raise RuntimeError("vertex 429 resource exhausted")

    jobs = SimpleNamespace(
        claim=lambda jid: job,
        lease=lambda j: nullcontext(),
        defer=lambda j, reason: calls.append(("defer", reason)),
        finish=lambda jid, status, error=None, token=None: calls.append((status, error)),
    )
    o = SimpleNamespace(
        jobs=jobs, store=SimpleNamespace(worker_fence=lambda j: nullcontext()), process=unavailable
    )
    return o, calls


@pytest.mark.parametrize("attempt", range(1, MAX_JOB_ATTEMPTS))
def test_transient_provider_failures_are_retried_within_the_budget(attempt):
    o, calls = runtime(attempt)
    with pytest.raises(RuntimeError):
        process_job(o, "J")
    assert calls == [("defer", "CLOUD_PROCESSING_RETRY")]


def test_failure_is_final_only_after_the_last_attempt():
    o, calls = runtime(MAX_JOB_ATTEMPTS)
    with pytest.raises(RuntimeError):
        process_job(o, "J")
    assert calls == [("failed", "CLOUD_PROCESSING_FAILED")]
    assert MAX_JOB_ATTEMPTS == 6  # Kept equal to the Cloud Tasks max_attempts.
