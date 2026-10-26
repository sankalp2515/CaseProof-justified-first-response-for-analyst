import json
import os
import sqlite3
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException

from caseproof.domain.contracts import hash_json
from mock_services.customer import response

app = FastAPI(title="CaseProof fictional receiving bank and case system")
DB = Path(os.environ.get("DATA_DIR", "var")) / "mock_outbound.sqlite"


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=30)
    db.execute(
        (
            "CREATE TABLE IF NOT EXISTS messages(key TEXT PRIMARY KEY,k"
            "ind TEXT,digest TEXT,response TEXT)"
        )
    )
    return db


@app.get("/health")
def health():
    return {"ok": True, "synthetic": True, "official_report": False}


@app.post("/{kind}")
def receive(kind: str, payload: dict, idempotency_key: str = Header(default="")):
    if kind not in ("cfcfrms_report_update", "case_ticket", "urgent_referral"):
        raise HTTPException(404, "unknown action")
    if payload.get("synthetic") is not True or not idempotency_key or len(idempotency_key) > 200:
        raise HTTPException(422, "synthetic payload and bounded idempotency key required")
    digest = hash_json(payload)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute(
            "SELECT kind,digest,response FROM messages WHERE key=?", (idempotency_key,)
        ).fetchone()
        if old:
            if old[0] != kind or old[1] != digest:
                raise HTTPException(409, "idempotency mismatch")
            return json.loads(old[2])
        result = {
            "message_id": "SYNTH-" + kind.upper() + "-" + uuid.uuid4().hex[:12],
            "synthetic": True,
            "official_report": False,
            "status": "received_by_fictional_service",
        }
        db.execute(
            "INSERT INTO messages VALUES(?,?,?,?)",
            (idempotency_key, kind, digest, json.dumps(result)),
        )
        return result


@app.post("/customer/reply")
def customer(payload: dict):
    cid = payload.get("case_id", "")
    if not cid or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in cid):
        raise HTTPException(422, "invalid case ID")
    return response(Path("var/kit_v2"), cid, payload.get("catalogue_id", ""))
