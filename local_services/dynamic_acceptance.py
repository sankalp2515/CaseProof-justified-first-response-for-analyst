"""New, non-fixture customer and downstream account acceptance through running services."""

import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from caseproof.adapters.duckdb_bank import DuckDBBank
from caseproof.graph.store import GraphStore


def validate_new_receiver(settings, call, snapshot, wait_job, feed):
    prefix = "DYN-" + uuid.uuid4().hex[:10]
    customer_account, mule, receiver = prefix + "-C", prefix + "-M", prefix + "-NEW"
    current_time = datetime.now(timezone(timedelta(hours=5, minutes=30)))

    def stamp(minutes):
        return (current_time - timedelta(minutes=minutes)).isoformat()

    fresh = call(
        "POST",
        "/v1/cases",
        json={
            "customer_account": customer_account,
            "reported_at": stamp(0),
            "first_contact": stamp(68),
        },
    )
    cid = fresh["case_id"]
    root = dict(
        txn_id=prefix + "-ROOT",
        ts=stamp(39),
        from_account=customer_account,
        to_account=mule,
        amount_minor=10000,
        channel="UPI",
        reference="SYNTH-TX-" + prefix,
        source="ledger",
    )
    GraphStore(settings.duckdb_path).load_world(
        dict(
            accounts=[
                dict(
                    id=customer_account,
                    bank="Cedar",
                    label=customer_account,
                    kind="customer",
                    opening_balance=10000,
                ),
                dict(id=mule, bank="Lotus", label=mule, kind="beneficiary"),
            ],
            transfers=[root],
            complaint_links=[
                dict(
                    complaint_id=cid,
                    victim=customer_account,
                    txn_id=root["txn_id"],
                    disputed_amount=10000,
                    reported_at=stamp(0),
                )
            ],
            identifiers=[],
        )
    )
    DuckDBBank(settings.duckdb_path).load(
        [
            dict(
                txn_id=root["txn_id"],
                account=customer_account,
                amount_minor=10000,
                payee="new-payee@fictional.invalid",
                ts=root["ts"],
                reference=root["reference"],
                direction="debit",
            )
        ],
        [],
    )
    upload = call("POST", f"/v1/cases/{cid}/upload-links")
    token = urlsplit(upload["url"]).path.rsplit("/", 1)[1]
    submitted = call(
        "POST",
        f"/v1/customer/{token}/complete",
        json={
            "notes": (
                f"I paid INR 100 on {stamp(39)[:10]} at {stamp(39)[11:16]}. "
                "Caller asked for a safe account transfer."
            )
        },
    )
    wait_job(submitted["job_id"])
    assert snapshot(cid)["trail"]["summary"]["unaccounted"] == 10000
    hop = dict(
        txn_id=prefix + "-HOP",
        ts=stamp(23),
        from_account=mule,
        to_account=receiver,
        amount_minor=6000,
        channel="UPI",
        reference="HOP-REF",
        source="cfcfrms_update:" + prefix + "-U1",
    )
    assert (
        feed.post(
            "/v1/updates",
            json=dict(
                update_id=prefix + "-U1",
                account=mule,
                reporting_bank="Lotus",
                reported_at=stamp(8),
                credit_received=[root],
                onward_transfers=[hop],
                balance_minor=4000,
            ),
        ).status_code
        == 200
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        current = snapshot(cid)
        if current["trail"]["summary"]["recoverable"] == 4000:
            break
        time.sleep(0.3)
    assert current["trail"]["summary"] == {
        "recoverable": 4000,
        "unaccounted": 6000,
        "left_system": 0,
    }
    assert (
        feed.post(
            "/v1/updates",
            json=dict(
                update_id=prefix + "-U2",
                account=receiver,
                reporting_bank="Tulip",
                reported_at=stamp(6),
                credit_received=[hop],
                onward_transfers=[],
                balance_minor=6000,
            ),
        ).status_code
        == 200
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        current = snapshot(cid)
        if current["trail"]["summary"]["recoverable"] == 10000:
            break
        time.sleep(0.3)
    assert current["trail"]["summary"]["recoverable"] == 10000
    assert next(a["bank"] for a in current["trail"]["accounts"] if a["id"] == receiver) == "Tulip"
    call(
        "POST",
        f"/v1/cases/{cid}/reviews",
        role="reviewer",
        json={
            "expected_revision": current["revision"],
            "digest": current["digest"],
            "disposition": "COMPLETE_HANDOFF",
            "reason": "SIMULATED new-account feed validation",
        },
    )
    packet = call("POST", f"/v1/cases/{cid}/exports", role="reviewer")["packet"]
    assert packet["report_update"]["unaccounted_amount_minor"] == 0
    assert all(p["observation_source"] for p in packet["report_update"]["traced_amounts"])
    return cid
