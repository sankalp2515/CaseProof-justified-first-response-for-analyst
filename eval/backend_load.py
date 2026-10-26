"""Declared small-sample local load: OCR overlap and actual victim HTTP/worker jobs."""

import argparse
import json
import math
import os
import platform
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from eval.backend_quality import load_frozen


def percentile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def checked(response):
    response.raise_for_status()
    return response.json()


def ocr_batch(data, size, url):
    barrier = threading.Barrier(size)

    def one(index):
        barrier.wait(timeout=10)
        start = time.perf_counter()
        row = {"index": index, "start": start, "error": None}
        try:
            response = httpx.post(
                url + "/v1/transcribe",
                content=data,
                timeout=45,
                trust_env=False,
                headers={"Content-Type": "image/png"},
            )
            row["http_status"] = response.status_code
            result = checked(response)
            row["lines"] = len(result["lines"])
            row["provider"] = result["provider"]
            row["passed"] = bool(result["lines"]) and result["provider"] == "tesseract"
        except Exception as error:
            row["error"] = type(error).__name__ + ": " + str(error)
            row["passed"] = False
        row["end"] = time.perf_counter()
        row["elapsed_ms"] = (row["end"] - start) * 1000
        return row

    with ThreadPoolExecutor(max_workers=size) as pool:
        return list(pool.map(one, range(size)))


def prepare_clients(base, sessions=1, needed=5):
    clients = []
    for _ in range(sessions):
        setup = httpx.Client(base_url=base, timeout=180, trust_env=False)
        checked(setup.post("/v1/victim/demo-session"))
        customers = checked(setup.get("/v1/victim/demo-customers"))["customers"]
        for customer in customers:
            client = httpx.Client(
                base_url=base, timeout=120, trust_env=False, cookies=setup.cookies
            )
            checked(client.post("/v1/victim/sessions", json={"customer_id": customer["account"]}))
            me = checked(client.get("/v1/victim/me"))
            tx = next((t for t in me["transactions"] if t["txn_id"].endswith("-T1")), None)
            if tx:
                response = client.get("/v1/victim/receipts/" + tx["txn_id"])
                response.raise_for_status()
                clients.append((client, tx, response.content))
            else:
                client.close()
        setup.close()
    assert len(clients) >= needed
    return clients


def complaint_batch(clients, size):
    barrier = threading.Barrier(size)

    def one(index):
        client, tx, data = clients[index]
        barrier.wait(timeout=10)
        started = time.perf_counter()
        row = {
            "start": started,
            "error": None,
            "accepted": False,
            "observed_job_states": [],
            "harness_retries": 0,
        }
        try:
            body = {
                "submission_id": "load-" + uuid.uuid4().hex,
                "narrative": (
                    "A caller pretended to be a bank officer. I sent money to a safe account."
                ),
                "transaction_ids": [tx["txn_id"]],
                "payment_authorisation": "deceived",
            }
            result = checked(client.post("/v1/victim/complaints", json=body))
            cid = result["case_id"]
            row.update(case_id=cid, accepted=True)
            duplicate = checked(client.post("/v1/victim/complaints", json=body))
            row["idempotent_submission"] = result == duplicate
            checked(
                client.post(
                    f"/v1/victim/complaints/{cid}/artifacts",
                    files={"file": ("receipt.png", data, "image/png")},
                    data={"kind": "receipt"},
                )
            )
            row["upload_ms"] = (time.perf_counter() - started) * 1000
            enqueued = time.perf_counter()
            first_running = None
            while time.perf_counter() - started < 120:
                workflow = checked(client.get(f"/v1/cases/{cid}/workflow"))
                job = workflow.get("job") or {}
                status = job.get("status")
                sample = {
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    "id": job.get("job_id"),
                    "status": status,
                }
                if (
                    not row["observed_job_states"]
                    or row["observed_job_states"][-1]["status"] != status
                ):
                    row["observed_job_states"].append(sample)
                if status == "running" and first_running is None:
                    first_running = time.perf_counter()
                if status == "failed":
                    row["provider_error"] = job.get("error")
                    break
                snap = checked(client.get(f"/v1/cases/{cid}"))
                receipt_ids = {
                    a["artifact_id"] for a in snap["artifacts"] if a["kind"] == "receipt"
                }
                processed = any(
                    s["artifact_id"] in receipt_ids and s["source"] == "model_ocr"
                    for s in snap["segments"]
                )
                if (
                    processed
                    and status not in {"queued", "running", "failed"}
                    and workflow["revision"] == snap["revision"]
                    and workflow["digest"] == snap["digest"]
                ):
                    row["completed"] = True
                    row["completed_revision"] = snap["revision"]
                    row["completed_digest"] = snap["digest"]
                    row["safe_readiness"] = snap["readiness"]["disposition"] != "COMPLETE_CANDIDATE"
                    row["image_ocr_lines"] = sum(
                        s["source"] == "model_ocr" for s in snap["segments"]
                    )
                    row["local_only"] = all(r["mode"] == "local" for r in snap["run_meta"])
                    break
                time.sleep(0.15)
            row["queue_wait_observed_ms"] = (
                (first_running - enqueued) * 1000 if first_running else None
            )
            row["queue_wait_note"] = (
                "Polling estimate; null means running transition was not observed."
            )
            audit = checked(client.get(f"/v1/cases/{cid}/audit"))
            revisions = [a["revision"] for a in audit if a["event"] == "processed"]
            row["no_duplicate_publication"] = len(revisions) == len(set(revisions))
            row["processed_publications"] = len(revisions)
            metrics_path = os.environ.get("JOBS_METRICS_DB")
            if metrics_path:
                with sqlite3.connect("file:" + metrics_path + "?mode=ro", uri=True) as db:
                    db.row_factory = sqlite3.Row
                    jobs = [
                        dict(r)
                        for r in db.execute(
                            "SELECT job_id,revision,status,enqueued_at,started_at,"
                            "finished_at,attempt_count "
                            "FROM jobs WHERE case_id=? ORDER BY revision",
                            (cid,),
                        ).fetchall()
                    ]
                row["persisted_jobs"] = jobs
                row["worker_retries_or_reclaims"] = sum(
                    max(0, j["attempt_count"] - 1) for j in jobs
                )
                waits = [
                    (j["started_at"] - j["enqueued_at"]) * 1000
                    for j in jobs
                    if j["started_at"] is not None and j["enqueued_at"] is not None
                ]
                row["max_persisted_queue_wait_ms"] = max(waits) if waits else None
                row["failed_jobs"] = sum(j["status"] == "failed" for j in jobs)
                row["captured_queue_drained"] = not any(
                    j["status"] in {"queued", "running"} for j in jobs
                )
        except Exception as error:
            row["error"] = type(error).__name__ + ": " + str(error)
        row["end"] = time.perf_counter()
        row["elapsed_ms"] = (row["end"] - started) * 1000
        row["passed"] = (
            not row["error"]
            and row.get("completed", False)
            and row.get("idempotent_submission", False)
            and row.get("no_duplicate_publication", False)
            and row.get("safe_readiness", False)
            and row.get("local_only", False)
            and row.get("captured_queue_drained", True)
            and row["elapsed_ms"] <= 120000
        )
        return row

    with ThreadPoolExecutor(max_workers=size) as pool:
        return list(pool.map(one, range(size)))


def run(folder, output, phase, sizes=(1, 3, 5), repetitions=3, sessions=1):
    corpus = load_frozen(folder)
    output.mkdir(parents=True, exist_ok=False)
    asset = corpus["cases"][0]["assets"][0]
    data = (folder / asset["path"]).read_bytes()
    clients = (
        prepare_clients(os.environ.get("API_BASE_URL", "http://gateway"), sessions, max(sizes))
        if phase == "http"
        else []
    )
    batches = []
    run_started = time.perf_counter()
    try:
        for size in sizes:
            for repetition in range(repetitions):
                rows = (
                    complaint_batch(clients, size)
                    if phase == "http"
                    else ocr_batch(data, size, os.environ.get("LOCAL_OCR_URL", "http://ocr:8000"))
                )
                latency = [r["elapsed_ms"] for r in rows]
                batch = {
                    "size": size,
                    "repetition": repetition + 1,
                    "rows": rows,
                    "p50_ms": percentile(latency, 0.5),
                    "p95_ms": percentile(latency, 0.95),
                    "all_requests_overlap": max(r["start"] for r in rows)
                    < min(r["end"] for r in rows),
                    "passed": all(r["passed"] for r in rows),
                }
                batches.append(batch)
                (output / f"batch-{size}-{repetition + 1}.json").write_text(
                    json.dumps(batch, indent=2)
                )
                print(
                    phase, size, repetition + 1, batch["passed"], round(batch["p95_ms"]), flush=True
                )
    finally:
        for client, _, _ in clients:
            client.close()
    report = {
        "phase": phase,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "budget_ms": 120000 if phase == "http" else 45000,
        "small_sample_tail_not_production_percentile": True,
        "corpus_sha256": (folder / "SHA256").read_text(),
        "batches": batches,
        "sizes": list(sizes),
        "repetitions": repetitions,
        "wall_seconds": round(time.perf_counter() - run_started, 1),
        "passed": len(batches) == len(sizes) * repetitions and all(b["passed"] for b in batches),
        "total_requests": sum(len(b["rows"]) for b in batches),
        "errors": sum(not r["passed"] for b in batches for r in b["rows"]),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["ocr", "http"])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", default="1,3,5", help="comma-separated batch sizes")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--sessions", type=int, default=1, help="practice sessions for clients")
    args = parser.parse_args()
    sizes = tuple(int(x) for x in args.sizes.split(","))
    result = run(args.corpus, args.output, args.phase, sizes, args.repetitions, args.sessions)
    raise SystemExit(0 if result["passed"] else 1)
