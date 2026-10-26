"""Durable local substitute for downstream bank events and later Pub/Sub ingestion."""

import json
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException

from caseproof.adapters.local_trail_feed import validate_updates
from caseproof.config import Settings
from caseproof.domain.contracts import hash_json

app = FastAPI(title="CaseProof local downstream bank feed")


def connect():
    path = Path(os.environ.get("DATA_DIR", "var")) / "feed.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS updates(id TEXT PRIMARY KEY,digest TEXT,data TEXT)"
    )
    return connection


def seed():
    path = Settings().trail_feed_path
    if not path.exists():
        return
    with connect() as db:
        for row in json.loads(path.read_text(encoding="utf-8")):
            db.execute(
                "INSERT OR IGNORE INTO updates VALUES(?,?,?)",
                (row["update_id"], hash_json(row), json.dumps(row)),
            )


@app.get("/health")
def health():
    seed()
    return {"ok": True, "synthetic": True, "transport": "local-http"}


@app.get("/v1/updates")
def updates(as_of: str):
    seed()
    with connect() as db:
        rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM updates")]
    return validate_updates(rows, as_of)


@app.post("/v1/updates")
def receive(row: dict):
    try:
        validate_updates([row], row["reported_at"])
        digest = hash_json(row)
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT digest FROM updates WHERE id=?", (row["update_id"],)
            ).fetchone()
            if prior and prior[0] != digest:
                raise HTTPException(409, "update ID already has different content")
            db.execute(
                "INSERT OR IGNORE INTO updates VALUES(?,?,?)",
                (row["update_id"], digest, json.dumps(row)),
            )
        return {"update_id": row["update_id"], "duplicate": bool(prior), "synthetic": True}
    except (KeyError, ValueError, TypeError):
        raise HTTPException(422, "invalid downstream update") from None
