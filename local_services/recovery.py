"""Fault injection against this Compose project's own services only.

Run as a disposable validation job with the Docker socket mounted (see the
`recovery-check` service in compose.yaml). It creates one synthetic practice
session and new complaints through the public frontend; it never mutates an
existing case and never targets containers outside this Compose project.
"""

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import httpx

SERVICES = ("api", "worker", "ocr", "trail-feed", "simulator", "frontend")


def main():
    project = os.environ.get("DOCKER_PROJECT", "caseproof")
    docker = httpx.Client(
        transport=httpx.HTTPTransport(uds="/var/run/docker.sock"),
        base_url="http://docker",
        timeout=60,
    )
    base = os.environ.get("API_BASE_URL", "http://frontend:8080")
    staff = httpx.Client(base_url=base, timeout=30, trust_env=False)

    def containers(service):
        """Every replica of a service in this project (scaled workers included)."""
        filters = {
            "label": [
                "com.docker.compose.project=" + project,
                "com.docker.compose.service=" + service,
            ]
        }
        response = docker.get(
            "/containers/json", params={"all": True, "filters": json.dumps(filters)}
        )
        response.raise_for_status()
        rows = [
            r for r in response.json() if r["Labels"].get("com.docker.compose.oneoff") != "True"
        ]
        assert rows, (service, "expected at least one owned service container")
        assert all(r["Labels"]["com.docker.compose.project"] == project for r in rows)
        return [r["Id"] for r in rows]

    def control(service, action, **params):
        for cid in containers(service):
            result = docker.post(f"/containers/{cid}/{action}", params=params)
            if action == "start" and result.status_code == 409:
                if docker.get(f"/containers/{cid}/json").json()["State"].get("Restarting"):
                    continue
            assert result.status_code in (204, 304), (service, action, result.status_code)

    def ready(service):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            states = [
                docker.get(f"/containers/{cid}/json").json()["State"] for cid in containers(service)
            ]
            if all(s["Running"] and s.get("Health", {}).get("Status") == "healthy" for s in states):
                return
            time.sleep(0.5)
        raise AssertionError(service + " did not recover")

    def api(path, body=None, role="analyst", client=staff):
        response = client.request(
            "GET" if body is None else "POST", path, json=body, headers={"X-Demo-User": role}
        )
        response.raise_for_status()
        return response.json()

    def current_job(cid):
        return (api(f"/v1/cases/{cid}/workflow").get("job") or {}).get("job_id")

    def wait_job(cid, statuses, job_id=None, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            jid = job_id or current_job(cid)
            if jid:
                job = api("/v1/jobs/" + jid)
                if job["status"] in statuses:
                    return job
            time.sleep(0.1)
        raise AssertionError(f"job for {cid} did not reach {statuses}")

    # One practice session supplies synthetic customers with their own receipts.
    setup = httpx.Client(base_url=base, timeout=180, trust_env=False)
    setup.post("/v1/victim/demo-session").raise_for_status()
    customers = setup.get("/v1/victim/demo-customers").json()["customers"]
    victims = []
    for customer in customers:
        client = httpx.Client(base_url=base, timeout=120, trust_env=False, cookies=setup.cookies)
        client.post("/v1/victim/sessions", json={"customer_id": customer["account"]})
        me = client.get("/v1/victim/me").json()
        tx = next((t for t in me["transactions"] if t["txn_id"].endswith("-T1")), None)
        if tx:
            receipt = client.get("/v1/victim/receipts/" + tx["txn_id"])
            receipt.raise_for_status()
            victims.append((client, tx, receipt.content))
    assert len(victims) >= 2, "practice session needs two customers with receipts"

    def complain(victim):
        client, tx, data = victim
        body = {
            "submission_id": "recovery-" + uuid.uuid4().hex,
            "narrative": "A caller claiming to be my bank told me to move money to a safe account.",
            "transaction_ids": [tx["txn_id"]],
            "payment_authorisation": "deceived",
        }
        created = client.post("/v1/victim/complaints", json=body)
        created.raise_for_status()
        cid = created.json()["case_id"]
        uploaded = client.post(
            f"/v1/victim/complaints/{cid}/artifacts",
            files={"file": ("receipt.png", data, "image/png")},
            data={"kind": "receipt"},
        )
        uploaded.raise_for_status()
        return cid

    result = {}

    # 1. OCR outage: the job fails visibly, no OCR facts are fabricated, retry recovers.
    control("ocr", "stop", t=5)
    try:
        cid = complain(victims[0])
        failed = wait_job(cid, {"failed"})
        snapshot = api("/v1/cases/" + cid)
        assert failed["error"] == "LOCAL_OCR_ERROR", failed
        assert not any(s["source"] == "model_ocr" for s in snapshot["segments"])
        result["ocr_outage"] = {"case_id": cid, "safe_error": failed["error"], "no_fallback": True}
        print("OCR outage rejected safely without fabricated OCR facts", flush=True)
    finally:
        control("ocr", "start")
    ready("ocr")
    # Background work may have published a newer revision during the outage; then
    # the old failed job is correctly non-retryable and the current job is retried.
    retried = []
    deadline = time.monotonic() + 180
    while True:
        assert time.monotonic() < deadline, "case did not recover after OCR returned"
        job = api("/v1/jobs/" + current_job(cid))
        snapshot = api("/v1/cases/" + cid)
        if job["status"] == "done" and any(
            s["source"] == "model_ocr" for s in snapshot["segments"]
        ):
            break
        if job["status"] == "failed" and job["job_id"] not in retried:
            response = staff.post(
                "/v1/jobs/" + job["job_id"] + "/retry", headers={"X-Demo-User": "analyst"}
            )
            assert response.status_code in (200, 409), response.status_code
            retried.append(job["job_id"])
        time.sleep(0.5)
    result["ocr_retry"] = {"retried_jobs": retried, "recovered_revision": job["revision"]}
    print("OCR retry completed with real OCR segments", flush=True)

    # 2. Every worker replica killed mid-job: the lease is reclaimed after restart.
    cid = complain(victims[1])
    running = wait_job(cid, {"running"})
    control("worker", "kill", signal="SIGKILL")
    control("worker", "start")  # Idempotent if the restart policy already started it.
    ready("worker")
    completed = wait_job(cid, {"done", "stale"}, running["job_id"])
    assert completed["lease_token"] != running["lease_token"]
    result["worker_recovery"] = {
        "case_id": cid,
        "status": completed["status"],
        "replicas_killed": len(containers("worker")),
    }
    print("Killed worker lease reclaimed", flush=True)

    # 3. Every service restarts independently; persisted state is unchanged.
    target = os.environ.get("RECOVERY_CASE_ID") or cid
    before = api("/v1/cases/" + target)
    audit = api(f"/v1/cases/{target}/audit")
    artifact = before["artifacts"][0]
    content_path = f"/v1/cases/{target}/artifacts/{artifact['artifact_id']}/content"
    digest = hashlib.sha256(
        staff.get(content_path, headers={"X-Demo-User": "analyst"}).content
    ).hexdigest()
    assert digest == artifact["sha256"]
    for service in SERVICES:
        control(service, "restart", t=10)
    for service in SERVICES:
        ready(service)
    after = api("/v1/cases/" + target)
    assert (after["revision"], after["digest"]) == (before["revision"], before["digest"])
    assert api(f"/v1/cases/{target}/audit") == audit
    restored = staff.get(content_path, headers={"X-Demo-User": "analyst"}).content
    assert hashlib.sha256(restored).hexdigest() == artifact["sha256"]
    result["persistence"] = {
        "case_id": target,
        "revision": before["revision"],
        "services_restarted": list(SERVICES),
        "digest_unchanged": True,
        "audit_unchanged": True,
        "evidence_hash_unchanged": True,
    }
    result["passed"] = True
    output = Path(os.environ.get("RECOVERY_OUTPUT", "/out/recovery.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
