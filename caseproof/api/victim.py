"""Scoped, explicitly synthetic customer sessions and bank complaint intake."""

import hashlib
import json
import secrets
import time
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    File,
    Form,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from caseproof.adapters.customer_links import CustomerLinks
from caseproof.adapters.duckdb_bank import DuckDBBank
from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.api.demo_evidence import SampleEvidence, capabilities, render_sample
from caseproof.api.ui_views import victim_receipt
from caseproof.domain.contracts import hash_json, now
from local_services.demo_world import ADMIN, DemoWorld


class Session(BaseModel):
    customer_id: str


class Complaint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_id: str = Field(min_length=1, max_length=100)
    narrative: str = Field(min_length=5, max_length=10000)
    transaction_ids: list[str] = Field(default_factory=list, max_length=20)
    payment_authorisation: str = Field(pattern="^(deceived|unrecognised|unsure)$")
    first_contact: str | None = None
    bank_reference: str = Field(default="", max_length=120)
    ncrp_reference: str = Field(default="", max_length=120)
    fir_reference: str = Field(default="", max_length=120)


class PracticeScenario(BaseModel):
    """How long ago the synthetic scam payment happened (golden hour = 60 minutes)."""

    model_config = ConfigDict(extra="forbid")
    minutes_ago: int = Field(default=30, ge=5, le=240)


class PaymentDecision(BaseModel):
    transaction_id: str
    disputed: bool


def install(app, o):
    router = APIRouter()
    world = DemoWorld(o)
    links = CustomerLinks(o)

    def catalogue(request):
        sid = request.cookies.get("cp_demo")
        if sid:
            import re

            if not re.fullmatch(r"judge-[a-f0-9]{12}", sid):
                raise PermissionError("invalid demo session")
            chosen = DemoWorld(o, sid)
            if not chosen.path.exists():
                raise PermissionError("unknown demo session")
            return chosen.ensure()
        return world.ensure()

    app.state.demo_catalogue = catalogue

    @router.post("/v1/victim/demo-session")
    def new_practice_session(
        request: Request, response: Response, body: PracticeScenario | None = None
    ):
        enabled()
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise PermissionError("cross-origin session")
        # A chosen scam timing needs a world generated now; pooled worlds age.
        sid = DemoWorld.claim_ready(o) if body is None else None
        if sid is None:
            sid = "judge-" + uuid.uuid4().hex[:12]
            DemoWorld(o, sid).ensure(minutes_ago=(body or PracticeScenario()).minutes_ago)
        response.set_cookie("cp_demo", sid, httponly=True, samesite="strict", max_age=86400)
        response.delete_cookie("cp_victim")
        return {"session_id": sid, "synthetic": True, "complaints_created": 0}

    def dispatch(background_tasks):
        if not o.s.external_worker:
            from caseproof.worker import run_one

            background_tasks.add_task(run_one, o.jobs, o)

    with o.store.engine.begin() as db:
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS victim_sessions("
                "token TEXT PRIMARY KEY,account TEXT,expires REAL)"
            )
        )
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS victim_submissions(account TEXT,key TEXT,"
                "digest TEXT,result TEXT,PRIMARY KEY(account,key))"
            )
        )
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS victim_inbox(case_id TEXT,request_id TEXT,"
                "url TEXT,expires REAL,PRIMARY KEY(case_id,request_id))"
            )
        )
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS victim_payment_decisions(case_id TEXT,"
                "transaction_id TEXT,disputed INTEGER,at TEXT,PRIMARY KEY(case_id,transaction_id))"
            )
        )

    def enabled():
        if not (o.s.demo_mode and o.s.preloaded_demo and o.s.customer_portal):
            raise PermissionError("victim demo disabled")

    def customer(request: Request, cp_victim: str = Cookie(default="")):
        enabled()
        origin = request.headers.get("origin")
        if request.method != "GET" and origin and origin != str(request.base_url).rstrip("/"):
            raise PermissionError("cross-origin mutation")
        with o.store.engine.connect() as db:
            row = db.execute(
                text("SELECT account FROM victim_sessions WHERE token=:t AND expires>:at"),
                {"t": hash_json(cp_victim), "at": time.time()},
            ).first()
        if not row:
            raise PermissionError("customer session required")
        return world.customer(row[0])

    def owned(cid, person):
        meta = o.store.metadata(cid)
        if meta.get("customer_account") != person["account"] or meta["tenant_id"] != "demo":
            raise PermissionError("customer ownership mismatch")
        return meta

    @router.get("/report")
    def page():
        enabled()
        return FileResponse(Path(__file__).resolve().parents[1] / "inspector/victim.html")

    @router.get("/victim.js")
    def script():
        return FileResponse(Path(__file__).resolve().parents[1] / "inspector/victim.js")

    @router.get("/v1/victim/demo-customers")
    def people(request: Request):
        enabled()
        data = catalogue(request)
        return {
            "customers": data["customers"],
            "banks": data["banks"],
            "synthetic": True,
            "version": data.get("version", 1),
        }

    @router.post("/v1/victim/sessions")
    def session(body: Session, response: Response, request: Request):
        enabled()
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise PermissionError("cross-origin session")
        if body.customer_id not in {p["account"] for p in catalogue(request)["customers"]}:
            raise ValueError("unknown demo customer")
        token = secrets.token_urlsafe(32)
        with o.store.engine.begin() as db:
            db.execute(
                text("INSERT INTO victim_sessions VALUES(:t,:a,:e)"),
                {"t": hash_json(token), "a": body.customer_id, "e": time.time() + 86400},
            )
        response.set_cookie("cp_victim", token, httponly=True, samesite="strict", max_age=86400)
        response.headers["Cache-Control"] = "no-store"
        return {"synthetic": True}

    @router.get("/v1/victim/sample-evidence")
    def sample_capabilities(person=Depends(customer)):
        return capabilities(o)

    @router.post("/v1/victim/sample-evidence")
    def sample_evidence(body: SampleEvidence, person=Depends(customer)):
        transaction = next(
            (
                t
                for t in DuckDBBank(o.s.duckdb_path).transactions(person["account"])
                if t["txn_id"] == body.transaction_id
            ),
            None,
        )
        if transaction is None:
            raise PermissionError("payment not owned")
        image, generator = render_sample(o, person["account"], transaction, body)
        return Response(image, media_type="image/png", headers={"X-CaseProof-Generator": generator})

    @router.get("/v1/victim/me")
    def me(person=Depends(customer)):
        transactions = DuckDBBank(o.s.duckdb_path).transactions(person["account"])
        cases = [
            r["case_id"]
            for r in o.store.list_cases("demo")
            if o.store.metadata(r["case_id"]).get("customer_account") == person["account"]
        ]
        return {
            "customer": person,
            "transactions": transactions,
            "complaints": cases,
            "demo_time": now(),
        }

    @router.post("/v1/victim/complaints")
    def submit(body: Complaint, background_tasks: BackgroundTasks, person=Depends(customer)):
        transactions = {
            t["txn_id"]: t for t in DuckDBBank(o.s.duckdb_path).transactions(person["account"])
        }
        if any(t not in transactions for t in body.transaction_ids):
            raise ValueError("payment not owned by customer")
        if body.first_contact:
            from caseproof.domain.ledger import dt

            dt(body.first_contact)
        digest = hash_json(body.model_dump())
        # Account lock protects retries and isolates submission publication from the worker.
        with links.lock("victim-" + person["account"]):
            with o.store.engine.connect() as db:
                old = db.execute(
                    text(
                        "SELECT digest,result FROM victim_submissions WHERE account=:a AND key=:k"
                    ),
                    {"a": person["account"], "k": body.submission_id},
                ).first()
            if old:
                if old[0] != digest:
                    raise ConflictError("submission_content_changed")
                return json.loads(old[1])
            cid = (
                "CASE-"
                + hashlib.sha256((person["account"] + body.submission_id).encode()).hexdigest()[:16]
            )
            try:
                o.store.get(cid)
            except KeyError:
                o.store.create(
                    case_id=cid,
                    tenant_id="demo",
                    customer_account=person["account"],
                    reported_at=now(),
                    first_contact=body.first_contact
                    or min([transactions[t]["ts"] for t in body.transaction_ids] or [now()]),
                    contact_time_unknown=body.first_contact is None,
                    channel="bank_website",
                    selected_transaction_ids=list(dict.fromkeys(body.transaction_ids)),
                    submission_digest=digest,
                    payment_authorisation=body.payment_authorisation,
                    complaint_references={
                        "bank": body.bank_reference,
                        "ncrp": body.ncrp_reference,
                        "fir": body.fir_reference,
                    },
                )
            if o.store.metadata(cid).get("submission_digest") != digest:
                raise ConflictError("submission_content_changed")
            note = (
                body.narrative
                + "\nVictim reports suspected scam; payment authorisation account: "
                + body.payment_authorisation
            )
            from caseproof.domain.intake_priority import record_intake_priority

            record_intake_priority(o, cid, [transactions[t] for t in body.transaction_ids])
            # Content-addressed intake is safe to repeat after interrupted creation.
            o.intake.add(cid, note.encode(), "text/plain", "narrative")
            snap = o.store.get(cid)
            o.jobs.enqueue(cid, snap.revision, priority=10)
            dispatch(background_tasks)
            result = {"case_id": cid, "bank_reference": "CEDAR-" + cid[5:], "synthetic": True}
            with o.store.engine.begin() as db:
                db.execute(
                    text("INSERT INTO victim_submissions VALUES(:a,:k,:d,:r)"),
                    {
                        "a": person["account"],
                        "k": body.submission_id,
                        "d": digest,
                        "r": json.dumps(result),
                    },
                )
            return result

    @router.get("/v1/victim/complaints/{cid}")
    def complaint(cid: str, person=Depends(customer)):
        owned(cid, person)
        snap = o.store.get(cid)
        with o.store.engine.connect() as db:
            delivered = db.execute(
                text("SELECT count(*) FROM outbox WHERE case_id=:c AND status='sent'"),
                {"c": cid},
            ).scalar()
        messages = []
        for r in snap.requests:
            if r.state == "accepted":
                with o.store.engine.connect() as db:
                    item = db.execute(
                        text(
                            "SELECT url,expires FROM victim_inbox "
                            "WHERE case_id=:c AND request_id=:r"
                        ),
                        {"c": cid, "r": r.request_id},
                    ).first()
                messages.append(
                    {
                        "request_id": r.request_id,
                        "text": r.reason,
                        "reply_url": item[0] if item and item[1] > time.time() else None,
                    }
                )
        return {
            "case_id": cid,
            "status": (
                "Information requested"
                if messages
                else "Report update available"
                if delivered
                else "Being reviewed"
            ),
            "messages": messages,
            "evidence_count": len(snap.artifacts),
            "candidate_payments": [t.model_dump() for t in snap.unreported],
            "note": "A report acknowledgement does not mean money is held or recovered.",
            **victim_receipt(o, cid, snap),
        }

    @router.post("/v1/victim/complaints/{cid}/payments")
    def payment_decision(
        cid: str, body: PaymentDecision, background_tasks: BackgroundTasks, person=Depends(customer)
    ):
        owned(cid, person)
        tx = next(
            (
                t
                for t in DuckDBBank(o.s.duckdb_path).transactions(person["account"])
                if t["txn_id"] == body.transaction_id
            ),
            None,
        )
        if not tx:
            raise PermissionError("payment not owned")
        with links.lock(cid):
            snap = o.store.get(cid)
            with o.store.engine.begin() as db:
                old = db.execute(
                    text(
                        "SELECT disputed FROM victim_payment_decisions "
                        "WHERE case_id=:c AND transaction_id=:t"
                    ),
                    {"c": cid, "t": body.transaction_id},
                ).first()
                if old and bool(old[0]) != body.disputed:
                    raise ConflictError("payment_decision_requires_analyst_correction")
                if old:
                    return {"received": True}
                prior_revision = snap.revision
                snap.revision += 1
                snap.readiness.disposition = "REVIEW_REQUIRED"
                if not body.disputed:
                    snap.ledger_matches = [
                        m for m in snap.ledger_matches if m.txn_id != body.transaction_id
                    ]
                    snap.unreported = [
                        t for t in snap.unreported if t.txn_id != body.transaction_id
                    ]
                snap.trail.setdefault("victim_payment_decisions", []).append(
                    {"transaction_id": body.transaction_id, "disputed": body.disputed, "at": now()}
                )
                for r in snap.requests:
                    if r.state == "accepted" and r.catalogue_id == "confirm_additional_transfer":
                        r.state = "fulfilled"
                        r.reason = "Victim recorded a transaction-specific dispute decision."
                db.execute(
                    text("INSERT OR IGNORE INTO victim_payment_decisions VALUES(:c,:t,:d,:a)"),
                    {"c": cid, "t": body.transaction_id, "d": int(body.disputed), "a": now()},
                )
                o.store.publish(snap, prior_revision, "victim_payment_decision", connection=db)
                db.execute(
                    text(
                        "INSERT OR IGNORE INTO jobs(job_id,case_id,revision,status,error,priority) "
                        "VALUES(:j,:c,:r,'queued',NULL,10)"
                    ),
                    {"j": "JOB-" + uuid.uuid4().hex[:12], "c": cid, "r": snap.revision},
                )
            dispatch(background_tasks)
        return {"received": True}

    @router.post("/v1/victim/complaints/{cid}/artifacts")
    async def artifact(
        cid: str,
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        kind: str = Form("receipt"),
        person=Depends(customer),
    ):
        owned(cid, person)
        data = await file.read(5 * 1024 * 1024 + 1)
        if kind not in {"receipt", "messages", "call_log", "narrative"}:
            raise ValueError("unsupported evidence kind")
        with links.lock(cid):
            result = o.intake.add(cid, data, file.content_type, kind)
            o.jobs.enqueue(cid, result.revision, priority=10)
            dispatch(background_tasks)
        return {"uploaded": True}

    @router.get("/v1/victim/receipts/{txn_id}")
    def receipt(txn_id: str, person=Depends(customer)):
        tx = next(
            (
                t
                for t in DuckDBBank(o.s.duckdb_path).transactions(person["account"])
                if t["txn_id"] == txn_id
            ),
            None,
        )
        if not tx:
            raise PermissionError("payment not owned")
        # Reuse the independent bank receipt renderer for its primary debit.
        network = __import__("local_services.bank_network", fromlist=["BankNetwork"]).BankNetwork(o)
        saved = network.read(person["network_id"], ADMIN)
        if tx["txn_id"] != saved["dataset"]["transactions"][2]["txn_id"]:
            return Response((json.dumps(tx, indent=2)).encode(), media_type="text/plain")
        return Response(network.receipt(person["network_id"], ADMIN), media_type="image/png")

    app.include_router(router)
