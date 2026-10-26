"""End-to-end check of the deployed staging app through its public HTTPS edge.

Usage: python scripts/cloud_staging_check.py https://<domain>
Acts like one visitor: practice session, victim complaint with the bank's own
receipt image, real Document AI/Gemini processing, an analyst request answered by
the customer, a reviewer decision and delivery to both simulated receivers.
Everything is synthetic and confined to the new practice session.
"""

import json
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://8-233-217-230.sslip.io"
OUT = Path(__file__).resolve().parents[1] / "var/cloud-staging/e2e.json"
started = time.monotonic()
timeline = []


def mark(event, **detail):
    row = {"t": round(time.monotonic() - started, 1), "event": event, **detail}
    timeline.append(row)
    print(json.dumps(row), flush=True)


def until(label, probe, timeout=600, every=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(every)
    raise AssertionError(f"timed out waiting for {label}")


client = httpx.Client(base_url=BASE, timeout=120, follow_redirects=False)


def staff(role="analyst"):
    return {"X-Demo-User": role}


def ok(response):
    if response.status_code >= 400:
        raise AssertionError(
            f"{response.request.method} {response.request.url.path}: "
            f"{response.status_code} {response.text[:300]}"
        )
    return response.json() if response.content else {}


assert ok(client.get("/health"))["ok"]
assert client.get("/app/").status_code == 200
mark("edge_ready")

ok(client.post("/v1/victim/demo-session"))
catalogue = until(
    "practice bank data",
    lambda: (r := client.get("/v1/victim/demo-customers")).status_code == 200 and r.json(),
    timeout=300,
)
mark("practice_session_ready", customers=len(catalogue["customers"]))

me = None
for person in catalogue["customers"]:
    session = until(
        "victim session",
        lambda: (
            (
                r := client.post("/v1/victim/sessions", json={"customer_id": person["account"]})
            ).status_code
            != 503
            and r
        ),
        timeout=300,
    )
    ok(session)
    me = ok(
        until(
            "published bank records",
            lambda: (r := client.get("/v1/victim/me")).status_code != 503 and r,
            timeout=600,
        )
    )
    t1 = next((t for t in me["transactions"] if t["txn_id"].endswith("-T1")), None)
    if t1:
        break
assert t1, "no customer with a T1 payment"
receipt = client.get("/v1/victim/receipts/" + t1["txn_id"])
assert receipt.status_code == 200 and receipt.content[:4] == b"\x89PNG"
mark("victim_ready", account=me["customer"]["account"], payment=t1["txn_id"])

complaint = ok(
    client.post(
        "/v1/victim/complaints",
        json={
            "submission_id": "staging-" + uuid.uuid4().hex,
            "narrative": (
                "At about 10:00 today a man called saying he was from Cedar Bank's fraud team. "
                "He told me to move my money to a safe account he gave me. I made the payment "
                "while he stayed on the call. I did not share any OTP or PIN."
            ),
            "transaction_ids": [t1["txn_id"]],
            "payment_authorisation": "deceived",
        },
    )
)
cid = complaint["case_id"]
ok(
    client.post(
        f"/v1/victim/complaints/{cid}/artifacts",
        data={"kind": "receipt"},
        files={"file": ("receipt.png", receipt.content, "image/png")},
    )
)
mark("complaint_submitted", case_id=cid)


def processed():
    snap = ok(client.get(f"/v1/cases/{cid}", headers=staff()))
    flow = ok(client.get(f"/v1/cases/{cid}/workflow", headers=staff()))
    job = flow.get("job") or {}
    if job.get("status") == "failed":
        raise AssertionError(f"job failed: {job}")
    ocr = [s for s in snap["segments"] if s["source"] != "narrative"]
    return snap if ocr and job.get("status") not in {"queued", "running"} else None


snap = until("evidence processing", processed, timeout=900, every=5)
providers = sorted({(r["provider"], r["mode"]) for r in snap["run_meta"]})
mark(
    "processed",
    revision=snap["revision"],
    providers=providers,
    ocr_segments=sum(s["source"] != "narrative" for s in snap["segments"]),
    claims=len(snap["claims"]),
    readiness=snap["readiness"]["disposition"],
)

proposed = [r for r in snap["requests"] if r["state"] == "proposed"]
if proposed:
    sent = ok(
        client.post(f"/v1/cases/{cid}/requests/{proposed[0]['request_id']}/send", headers=staff())
    )
    token = sent["url"].rsplit("/", 1)[1]
    link = client.get(sent["url"].replace(BASE, ""), follow_redirects=False)
    assert link.status_code == 303 and "/app/#/victim/reply/" in link.headers["location"]
    assert ok(client.get(f"/v1/customer/{token}"))
    unreported = snap.get("unreported") or []
    note = (
        "I also do not recognise any other payment."
        if not unreported
        else f"The INR {unreported[0]['amount_minor'] / 100:.2f} payment is unrelated to this scam."
    )
    ok(client.post(f"/v1/customer/{token}/complete", json={"notes": note}))
    mark("request_answered", request=proposed[0]["kind"] if "kind" in proposed[0] else "request")
    previous = snap["revision"]
    snap = until(
        "reassessment",
        lambda: (s := processed()) and s["revision"] > previous and s,
        timeout=900,
        every=5,
    )
    mark("reassessed", revision=snap["revision"], readiness=snap["readiness"]["disposition"])

for candidate in snap.get("unreported") or []:
    # Explicit customer decision, as the reply page records it: not part of this scam.
    ok(
        client.post(
            f"/v1/victim/complaints/{cid}/payments",
            json={"transaction_id": candidate["txn_id"], "disputed": False},
        )
    )
    mark("payment_marked_unrelated", payment=candidate["txn_id"])
    previous = snap["revision"]
    snap = until(
        "reassessment after decision",
        lambda: (s := processed()) and s["revision"] > previous and s,
        timeout=900,
        every=5,
    )
    mark("reassessed", revision=snap["revision"], readiness=snap["readiness"]["disposition"])

DECISIONS = {"COMPLETE_CANDIDATE": "COMPLETE_HANDOFF", "ESCALATE_CANDIDATE": "ESCALATE_WITH_GAPS"}
if snap["readiness"]["disposition"] not in DECISIONS:
    # Bank coverage through the filing instant arrives from the scheduled reconcile.
    mark("waiting_for_bank_refresh", unresolved=snap["readiness"]["unresolved_facts"])
    snap = until(
        "decidable readiness",
        lambda: (s := processed()) and s["readiness"]["disposition"] in DECISIONS and s,
        timeout=600,
        every=10,
    )
    mark("reassessed", revision=snap["revision"], readiness=snap["readiness"]["disposition"])
decision = DECISIONS.get(snap["readiness"]["disposition"])
assert decision, f"not decidable: {snap['readiness']}"
ok(
    client.post(
        f"/v1/cases/{cid}/reviews",
        headers=staff("reviewer"),
        json={
            "expected_revision": snap["revision"],
            "digest": snap["digest"],
            "disposition": decision,
            "reason": "Staging check: reviewed cited evidence and bank records; gaps stated.",
        },
    )
)
mark("reviewed", disposition=decision)
ok(client.post(f"/v1/cases/{cid}/exports", headers=staff("reviewer")))


def delivered():
    flow = ok(client.get(f"/v1/cases/{cid}/workflow", headers=staff()))
    rows = flow.get("deliveries") or []
    sent = {d["kind"] for d in rows if d.get("status") == "sent"}
    return flow if flow["status"] == "completed" and len(sent) >= 2 else None


flow = until("both receivers acknowledged", delivered, timeout=600, every=5)
mark("delivered", destinations=[d.get("kind") for d in flow["deliveries"]], status=flow["status"])

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps(
        {
            "base": BASE,
            "case_id": cid,
            "passed": True,
            "providers": providers,
            "timeline": timeline,
        },
        indent=2,
    )
)
print(f"PASS in {timeline[-1]['t']}s; saved {OUT}")
