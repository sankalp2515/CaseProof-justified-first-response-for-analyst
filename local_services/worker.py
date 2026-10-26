"""Independent durable worker, with a health heartbeat and renewable per-job leases."""

import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from caseproof.config import Settings
from caseproof.domain.clock import current_clock, urgency
from caseproof.domain.contracts import hash_json, now
from caseproof.pipeline.orchestrator import Orchestrator
from caseproof.worker import run_one
from local_services.leadership import BackgroundLease, write_atomic


def poll_clocks(orchestrator):
    """Publish a new decision revision when a real clock crosses a policy urgency boundary."""
    for case in orchestrator.store.list_cases():
        snapshot = orchestrator.store.get(case["case_id"])
        if snapshot.clock and not snapshot.clock.replay and snapshot.clock.first_debit_at:
            from caseproof.domain.freshness import freshness_states

            current = current_clock(snapshot)
            if urgency(current) != urgency(snapshot.clock) or freshness_states(
                snapshot, current.as_of
            ) != freshness_states(snapshot, snapshot.clock.as_of):
                orchestrator.jobs.enqueue(snapshot.case_id, snapshot.revision)


def poll_feed(orchestrator):
    """Queue new revisions after durable feed changes, including previously approved cases."""
    settings = orchestrator.s
    if not settings.trail_feed_url:
        return
    result = httpx.get(
        settings.trail_feed_url + "/v1/updates",
        params={"as_of": now()},
        timeout=10,
        trust_env=False,
    )
    result.raise_for_status()
    rows = result.json()
    digest = hash_json(rows)
    cursor = settings.data_dir / "feed_cursor.json"
    previous = json.loads(cursor.read_text()) if cursor.exists() else None
    previous_hash = previous.get("hash") if isinstance(previous, dict) else previous
    if previous_hash != digest:
        if previous is not None:
            prior_ids = set(previous.get("ids", [])) if isinstance(previous, dict) else set()
            changed = [row for row in rows if row["update_id"] not in prior_ids]
            affected = {row["account"] for row in changed}
            for case in orchestrator.store.list_cases():
                snapshot = orchestrator.store.get(case["case_id"])
                accounts = {p["account"] for p in snapshot.trail.get("positions", [])}
                for transfer in snapshot.trail.get("transfers", []):
                    accounts.update((transfer["from_account"], transfer["to_account"]))
                if accounts & affected:
                    from sqlalchemy import text

                    from caseproof.adapters.sqlite_casestore import ConflictError

                    relevant = {r["update_id"] for r in changed if r["account"] in accounts}
                    observed = {
                        r["update_id"] for r in snapshot.trail.get("account_observations", [])
                    }
                    pending = set(snapshot.trail.get("pending_feed_update_ids", []))
                    try:
                        with orchestrator.store.engine.begin() as db:
                            last_activity = db.execute(
                                text(
                                    "SELECT max(at) FROM audit_events "
                                    "WHERE case_id=:c AND event IN "
                                    "('artifact_added','customer_link_issued','request_fulfilled',"
                                    "'approved','urgent_referral_approved','victim_payment_decision')"
                                ),
                                {"c": snapshot.case_id},
                            ).scalar()
                            recent = (
                                datetime.now(timezone.utc) - timedelta(minutes=15)
                            ).isoformat()
                            interactive = (
                                datetime.now(timezone.utc) - timedelta(minutes=2)
                            ).isoformat()
                            priority = (
                                10
                                if last_activity and last_activity >= interactive
                                else 5
                                if last_activity and last_activity >= recent
                                else 0
                            )
                            if relevant - observed - pending:
                                old = snapshot.revision
                                snapshot.revision += 1
                                snapshot.readiness.disposition = "REVIEW_REQUIRED"
                                snapshot.trail["pending_feed_update_ids"] = sorted(
                                    pending | relevant
                                )
                                orchestrator.store.publish(
                                    snapshot, old, "bank_feed_received", connection=db
                                )
                            db.execute(
                                text(
                                    "INSERT INTO jobs("
                                    "job_id,case_id,revision,status,error,priority) "
                                    "VALUES(:j,:c,:r,'queued',NULL,:p) "
                                    "ON CONFLICT(case_id,revision) DO UPDATE SET "
                                    "priority=max(jobs.priority,excluded.priority)"
                                ),
                                {
                                    "j": "JOB-"
                                    + hash_json([snapshot.case_id, snapshot.revision])[:12],
                                    "c": snapshot.case_id,
                                    "r": snapshot.revision,
                                    "p": priority,
                                },
                            )
                            db.execute(
                                text(
                                    "UPDATE jobs SET priority=max(priority,:p) "
                                    "WHERE case_id=:c AND revision=:r AND status='queued'"
                                ),
                                {"p": priority, "c": snapshot.case_id, "r": snapshot.revision},
                            )
                    except ConflictError:
                        latest = orchestrator.store.get(snapshot.case_id)
                        orchestrator.jobs.enqueue(latest.case_id, latest.revision)
    if previous_hash != digest or not isinstance(previous, dict):
        write_atomic(cursor, {"hash": digest, "ids": [r["update_id"] for r in rows]})


def main():
    import signal

    settings = Settings()
    heartbeat = settings.data_dir / "worker.heartbeat"
    if "--health" in sys.argv:
        raise SystemExit(
            0 if heartbeat.exists() and time.time() - heartbeat.stat().st_mtime < 20 else 1
        )
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    from local_services.health import replica_heartbeat

    # Shared heartbeat for API readiness (any live worker); per-replica for its healthcheck.
    own = replica_heartbeat(settings.data_dir)

    def pulse():
        while True:
            heartbeat.touch()
            own.touch()
            time.sleep(3)

    threading.Thread(target=pulse, daemon=True).start()
    orchestrator = Orchestrator(settings)
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    run_worker(orchestrator, stopped)


def poll_background(orchestrator, stopped):
    """Independent polling cannot block consumption of already-durable jobs."""
    settings = orchestrator.s
    from caseproof.adapters.bank_ingestion import BankIngestion
    from caseproof.adapters.http_outbound import recover_pending

    def refresh_demo():
        if settings.preloaded_demo:
            from local_services.demo_world import DemoWorld

            DemoWorld(orchestrator).tick()

    # Constructing ingestion runs schema setup under the shared bank-store lock;
    # build it once rather than every three seconds (it blocked practice sessions).
    ingestion = []

    def bank_wakeups():
        if not ingestion:
            ingestion.append(BankIngestion(orchestrator))
        ingestion[0].recover_wakeups()

    def practice_pool():
        if settings.preloaded_demo and settings.customer_portal:
            import uuid

            from local_services.demo_world import DemoWorld

            DemoWorld.fill_pool(orchestrator, lambda: "judge-" + uuid.uuid4().hex[:12])

    tasks = [
        ("bank_wakeups", bank_wakeups),
        ("outbound", lambda: recover_pending(orchestrator)),
        ("demo_observations", refresh_demo),
        ("feed", lambda: poll_feed(orchestrator)),
        ("clocks", lambda: poll_clocks(orchestrator)),
        ("practice_pool", practice_pool),
    ]
    # Only one replica polls; others keep processing leased jobs and stand by.
    lease = BackgroundLease(settings.data_dir)
    try:
        while not stopped.is_set():
            run_background_round(lease, tasks, stopped, settings)
            stopped.wait(3)
    finally:
        lease.release()


def run_background_round(lease, tasks, stopped, settings):
    """Run each task only while this replica holds (and renews) the polling lease."""
    for name, task in tasks:
        if stopped.is_set() or not lease.acquire():
            return
        try:
            task()
        except Exception as error:
            write_atomic(
                settings.data_dir / "feed_error.json",
                {"task": name, "error": type(error).__name__, "at": now()},
            )


def run_worker(orchestrator, stopped):
    background = threading.Thread(target=poll_background, args=(orchestrator, stopped), daemon=True)
    background.start()
    try:
        while not stopped.is_set():
            run_one(orchestrator.jobs, orchestrator)
            stopped.wait(0.25)
    finally:
        stopped.set()
        background.join(timeout=3)


if __name__ == "__main__":
    main()
