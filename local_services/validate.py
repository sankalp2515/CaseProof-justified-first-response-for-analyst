"""Black-box Docker acceptance: real local OCR, customer links, approval and delivery."""

import json
import os
import time
import uuid
from urllib.parse import urlsplit

import httpx

from caseproof.config import Settings


def main():
    settings = Settings()
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8080")
    client = httpx.Client(base_url=base, timeout=60, trust_env=False)
    checks = []

    def call(method, path, expected=200, role="analyst", **kwargs):
        response = client.request(method, path, headers={"X-Demo-User": role}, **kwargs)
        assert response.status_code == expected, (
            method,
            path,
            response.status_code,
            response.text[:200],
        )
        return response.json()

    def wait_job(job_id):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job = call("GET", "/v1/jobs/" + job_id)
            if job["status"] in {"done", "failed", "stale"}:
                assert job["status"] == "done", job
                return
            time.sleep(0.3)
        raise AssertionError("worker job timed out")

    def snapshot(cid):
        return call("GET", "/v1/cases/" + cid)

    created = call("POST", "/v1/local/fixtures/GOLD-001")
    cid = created["case_id"]
    wait_job(created["job_id"])
    initial = snapshot(cid)
    assert initial["clock"]["golden_hour_remaining"] == 21
    summary = initial["trail"]["summary"]
    assert summary["left_system"] == 864839
    assert summary["recoverable"] + summary["unaccounted"] == 6462561
    # Repeated validation preserves prior feed observations. A new equivalent report can
    # legitimately refresh part of this old GOLD world; never reset it to force a fixture total.
    from caseproof.domain.ledger import dt

    observed = {r["account"]: r for r in initial["trail"]["account_observations"]}
    for position in initial["trail"]["positions"]:
        if position["status"] == "recoverable":
            age = (
                dt(initial["clock"]["as_of"]) - dt(observed[position["account"]]["reported_at"])
            ).total_seconds()
            assert 0 <= age < 900
    assert initial["unreported"][0]["txn_id"] == "GOLD-T2"
    assert (
        initial["ledger_matches"][0]["resolved_fields"]["transaction_reference"] == "SYNTH-TX-0009"
    )
    assert all(r["mode"] == "local" for r in initial["run_meta"])
    assert any(
        s["ocr_model_id"]
        in {
            "tesseract-eng-hin-v1",
            "tesseract-eng-hin-psm6-v2",
            "tesseract-eng-hin-bounded-v3",
            "tesseract-eng-hin-bounded-v4",
            "tesseract-eng-hin-bounded-v5",
        }
        and s["box_2d"]
        for s in initial["segments"]
    )
    assert any(
        any("\u0900" <= char <= "\u097f" for char in s["text"])
        for s in initial["segments"]
        if s["source"] == "model_ocr"
    )
    checks.append(
        "real OCR and cited facts; 21-minute clock; ledger reference; exact sourced trail"
    )
    proposed = next(r for r in initial["requests"] if r["state"] == "proposed")
    assert proposed["catalogue_id"] == "confirm_additional_transfer", proposed
    call("POST", f"/v1/cases/{cid}/exports", expected=403)
    call("POST", f"/v1/cases/{cid}/exports", expected=409, role="reviewer")
    link = call("POST", f"/v1/cases/{cid}/requests/{proposed['request_id']}/send")
    token = urlsplit(link["url"]).path.rsplit("/", 1)[1]
    info = call("GET", "/v1/customer/" + token)
    assert "claim" not in json.dumps(info).lower() or "complaint" in info["request"]
    call("GET", "/v1/customer/" + "x" * 43, expected=403)
    source = json.loads((settings.eval_kit_v3 / "inputs/GOLD-001.json").read_text())
    for item in source["followup_artifacts"]:
        path = settings.eval_kit_v3 / item["path"]
        call(
            "POST",
            f"/v1/customer/{token}/artifacts",
            data={"kind": item["kind"]},
            files={"file": (path.name, path.read_bytes(), item["mime_type"])},
        )
    reply = call("POST", f"/v1/customer/{token}/complete", json={})
    call("GET", "/v1/customer/" + token, expected=403)
    wait_job(reply["job_id"])
    after = snapshot(cid)
    assert after["readiness"]["disposition"] == "COMPLETE_CANDIDATE", after["readiness"]
    assert {m["txn_id"] for m in after["ledger_matches"]} == {"GOLD-T1", "GOLD-T2"}
    assert not after["unreported"]
    delta = call("GET", f"/v1/cases/{cid}/revisions/{initial['revision']}/diff/{after['revision']}")
    assert delta["added"]
    checks.append(
        "one customer request, actual upload/reply portal, closed token, new revision and diff"
    )
    review = {
        "expected_revision": after["revision"],
        "digest": after["digest"],
        "disposition": "COMPLETE_HANDOFF",
        "reason": "Docker acceptance reviewer",
    }
    call("POST", f"/v1/cases/{cid}/reviews", expected=403, json=review)
    call("POST", f"/v1/cases/{cid}/reviews", role="reviewer", json=review)
    first = call("POST", f"/v1/cases/{cid}/exports", role="reviewer")
    assert first["packet"]["audit"]["mode"] == "local"
    second = call("POST", f"/v1/cases/{cid}/exports", role="reviewer")
    assert first == second
    report = first["packet"]["report_update"]
    assert {d["txn_id"] for d in report["debits"]} == {"GOLD-T1", "GOLD-T2"}
    assert all(d["reference"] and d["sources"] for d in report["debits"])
    assert len(first["outbound"]) == 2
    assert all(p["path"] and p["sources"] for p in report["traced_amounts"])
    checks.append("reviewer-only exact approval, two sourced deliveries, idempotent resend")
    # New evidence must immediately invalidate the exact approval, even before processing.
    call(
        "POST",
        f"/v1/cases/{cid}/artifacts",
        data={"kind": "narrative", "stage": "followup"},
        files={
            "file": (
                "note.txt",
                b"Additional analyst note for stale approval validation.",
                "text/plain",
            )
        },
    )
    call("POST", f"/v1/cases/{cid}/exports", expected=409, role="reviewer")
    call("POST", f"/v1/cases/{cid}/reviews", expected=409, role="reviewer", json=review)
    checks.append("new evidence invalidates approval; stale approval and send return 409")
    # An independent complaint starts through a customer upload, not a seeded artifact path.
    customer_case = call(
        "POST",
        "/v1/cases",
        json={
            "customer_account": "SYNTH-PORTAL-" + uuid.uuid4().hex[:8],
            "reported_at": "2026-10-01T12:08:00+05:30",
            "first_contact": "2026-10-01T11:00:00+05:30",
        },
    )
    new_id = customer_case["case_id"]
    initial_link = call("POST", f"/v1/cases/{new_id}/upload-links")
    initial_token = urlsplit(initial_link["url"]).path.rsplit("/", 1)[1]
    call(
        "POST",
        f"/v1/customer/{initial_token}/artifacts",
        expected=422,
        data={"kind": "receipt"},
        files={"file": ("fake.png", b"not an image", "image/png")},
    )
    result = call(
        "POST",
        f"/v1/customer/{initial_token}/complete",
        json={
            "notes": (
                "I paid INR 100 on 2026-10-01 at 11:29. Caller asked for a safe account transfer."
            )
        },
    )
    wait_job(result["job_id"])
    assert snapshot(new_id)["claims"]
    checks.append("new customer complaint upload, MIME signature rejection, durable job processing")
    # Duplicate downstream events are harmless, changed reuse of the same ID is rejected.
    # Re-approve the current evidence revision so the next invalidation is caused only by the feed.
    processed = call("POST", f"/v1/cases/{cid}/process")
    wait_job(processed["job_id"])
    current = snapshot(cid)
    call(
        "POST",
        f"/v1/cases/{cid}/reviews",
        role="reviewer",
        json={
            "expected_revision": current["revision"],
            "digest": current["digest"],
            "disposition": "COMPLETE_HANDOFF",
            "reason": "SIMULATED feed invalidation check",
        },
    )
    feed = httpx.Client(base_url=settings.trail_feed_url, timeout=10, trust_env=False)
    event = json.loads(settings.trail_feed_path.read_text())[0]
    assert feed.post("/v1/updates", json=event).status_code == 200
    changed = dict(event, balance_minor=event["balance_minor"] + 1)
    assert feed.post("/v1/updates", json=changed).status_code == 409
    # A new equivalent balance observation must trigger a new analyst revision automatically.
    observed = dict(
        event,
        update_id="VALIDATION-" + uuid.uuid4().hex,
        reported_at="2026-10-01T12:00:00+05:30",
        credit_received=[],
        onward_transfers=[],
    )
    before_feed = snapshot(cid)["revision"]
    assert feed.post("/v1/updates", json=observed).status_code == 200
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and snapshot(cid)["revision"] <= before_feed:
        time.sleep(0.5)
    assert snapshot(cid)["revision"] > before_feed
    call("POST", f"/v1/cases/{cid}/exports", expected=409, role="reviewer")
    checks.append(
        "persistent feed delivery, update-ID conflict rejection, automatic trail revision"
    )
    from local_services.dynamic_acceptance import validate_new_receiver

    dynamic_case = validate_new_receiver(settings, call, snapshot, wait_job, feed)
    checks.append(
        "new receiver discovered from local feed; unobserved funds stay unaccounted; "
        "a later bank observation supports recovery and approval"
    )
    audit = call("GET", f"/v1/cases/{cid}/audit")
    assert any(e["event"] == "approved" for e in audit)
    assert any(e["event"] == "request_fulfilled" for e in audit)
    result = {
        "passed": True,
        "dynamic_case_id": dynamic_case,
        "case_id": cid,
        "checks": checks,
        "llm": "local Tesseract + literal rules; no cloud, cache or renderer transcripts",
        "packet_id": first["packet"]["packet_id"],
    }
    (settings.data_dir / "local_validation.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
