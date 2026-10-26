import json
from urllib.parse import urlparse

import httpx
from sqlalchemy import text

from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.domain.contracts import hash_json
from caseproof.domain.packet import build_packet
from caseproof.domain.review import approved_snapshot


class HTTPOutbound:
    def __init__(self, url, allowed_hosts=()):
        u = urlparse(url)
        if (
            u.hostname not in {"127.0.0.1", "localhost", "::1", *allowed_hosts}
            or u.scheme != "http"
        ):
            raise ValueError("only loopback mock services permitted")
        self.url = url.rstrip("/")

    def send(self, kind, payload, idempotency_key):
        if (
            kind not in ("cfcfrms_report_update", "case_ticket", "urgent_referral")
            or payload.get("synthetic") is not True
        ):
            raise ValueError("synthetic outbound only")
        r = httpx.post(
            self.url + "/" + kind,
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
            timeout=15,
            trust_env=False,
        )
        r.raise_for_status()
        return r.json()


def prepare_export(o, case_id):
    """Commit both immutable delivery intents before attempting any network operation."""
    snapshot, approval = approved_snapshot(o.store, case_id)
    packet = build_packet(snapshot, approval)
    from caseproof.domain.freshness import require_fresh_handoff

    with o.store.engine.begin() as db:
        if (
            db.execute(
                text("UPDATE cases SET revision=revision WHERE case_id=:c AND revision=:r"),
                {"c": case_id, "r": snapshot.revision},
            ).rowcount
            != 1
        ):
            raise ConflictError("stale_export")
        for kind in ("cfcfrms_report_update", "case_ticket"):
            payload = (
                packet.report_update
                if kind == "cfcfrms_report_update"
                else packet.model_dump(mode="json")
            )
            key = hash_json({"packet_id": packet.packet_id, "kind": kind})
            old = db.execute(
                text("SELECT payload,status FROM outbox WHERE key=:k"), {"k": key}
            ).first()
            if old and hash_json(json.loads(old[0])) != hash_json(payload):
                raise ConflictError("packet_payload_changed_reprocess_and_reapprove")
            if old and old[1] == "sent":
                continue
            require_fresh_handoff(
                snapshot, require_coverage=approval.disposition == "COMPLETE_HANDOFF"
            )
            db.execute(
                text("INSERT OR IGNORE INTO outbox VALUES(:k,:c,:r,:kind,:p,'pending',NULL)"),
                {
                    "k": key,
                    "c": case_id,
                    "r": snapshot.revision,
                    "kind": kind,
                    "p": json.dumps(payload),
                },
            )
    return packet


def dispatch(o, key):
    """Stable delivery key handles a lost acknowledgement; stale intents cannot dispatch."""
    try:
        with o.store.engine.begin() as db:
            # Serialize against evidence publication while the approved request is sent.
            db.execute(
                text(
                    "UPDATE cases SET revision=revision WHERE case_id="
                    "(SELECT case_id FROM outbox WHERE key=:k)"
                ),
                {"k": key},
            )
            row = (
                db.execute(text("SELECT * FROM outbox WHERE key=:k"), {"k": key}).mappings().first()
            )
            if not row:
                raise KeyError("delivery intent missing")
            if row["status"] == "sent":
                return json.loads(row["response"])
            snapshot = o.store.get(row["case_id"])
            payload = json.loads(row["payload"])
            if snapshot.revision != row["revision"] or snapshot.digest != payload.get(
                "digest", payload.get("audit", {}).get("digest")
            ):
                raise ConflictError("stale_export")
            if row["kind"] == "urgent_referral":
                from caseproof.domain.referral import describe

                if not describe(snapshot)["eligible"]:
                    raise ConflictError("stale_referral")
            else:
                from caseproof.domain.contracts import Approval
                from caseproof.domain.freshness import require_fresh_handoff

                a = db.execute(
                    text("SELECT data FROM approvals WHERE case_id=:c AND revision=:r"),
                    {"c": row["case_id"], "r": row["revision"]},
                ).scalar()
                if not a or Approval.model_validate_json(a).approval_id != payload.get(
                    "approval_id"
                ):
                    raise ConflictError("approval_required_or_stale")
                require_fresh_handoff(
                    snapshot,
                    require_coverage=Approval.model_validate_json(a).disposition
                    == "COMPLETE_HANDOFF",
                )
            receipt = HTTPOutbound(o.s.mock_services_url, o.s.local_service_hosts).send(
                row["kind"], payload, key
            )
            db.execute(
                text("UPDATE outbox SET status='sent',response=:p WHERE key=:k"),
                {"p": json.dumps(receipt), "k": key},
            )
            if row["kind"] == "urgent_referral":
                db.execute(
                    text("INSERT OR IGNORE INTO urgent_deliveries VALUES(:a,:d)"),
                    {"a": payload["approval_id"], "d": json.dumps(receipt)},
                )
            return receipt
    except Exception as error:
        import time

        with o.store.engine.begin() as db:
            db.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS outbound_attempts "
                    "(key TEXT PRIMARY KEY,attempts INTEGER,next_at REAL,error TEXT)"
                )
            )
            n = (
                db.execute(
                    text("SELECT attempts FROM outbound_attempts WHERE key=:k"), {"k": key}
                ).scalar()
                or 0
            )
            n += 1
            db.execute(
                text(
                    "INSERT INTO outbound_attempts VALUES(:k,:n,:at,:e) "
                    "ON CONFLICT(key) DO UPDATE SET attempts=:n,next_at=:at,error=:e"
                ),
                {"k": key, "n": n, "at": time.time() + min(300, 2**n), "e": type(error).__name__},
            )
            terminal = isinstance(error, (ConflictError, ValueError)) or n >= 5
            if terminal:
                db.execute(
                    text("UPDATE outbox SET status=:s WHERE key=:k AND status!='sent'"),
                    {"k": key, "s": "stale" if isinstance(error, ConflictError) else "failed"},
                )
        raise


def recover_pending(o, force=False):
    import time

    with o.store.engine.begin() as db:
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS outbound_attempts "
                "(key TEXT PRIMARY KEY,attempts INTEGER,next_at REAL,error TEXT)"
            )
        )
        keys = [
            r[0]
            for r in db.execute(
                text(
                    "SELECT o.key FROM outbox o LEFT JOIN outbound_attempts a ON o.key=a.key "
                    "WHERE o.status='pending' AND (:force OR coalesce(a.next_at,0)<=:at) LIMIT 10"
                ),
                {"force": force, "at": time.time()},
            )
        ]
    for key in keys:
        try:
            dispatch(o, key)
        except Exception:
            pass  # failure/backoff is persisted by dispatch, never presented as success
    return len(keys)


def export(o, case_id):
    packet = prepare_export(o, case_id)
    responses = [
        dispatch(o, hash_json({"packet_id": packet.packet_id, "kind": kind}))
        for kind in ("cfcfrms_report_update", "case_ticket")
    ]
    p = o.s.data_dir / "packets"
    p.mkdir(parents=True, exist_ok=True)
    (p / (packet.packet_id + ".json")).write_text(
        packet.model_dump_json(indent=2), encoding="utf-8"
    )
    return {"packet": packet.model_dump(), "outbound": responses}
