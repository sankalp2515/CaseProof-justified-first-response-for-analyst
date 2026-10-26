from pathlib import Path
from typing import Any, Literal

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from caseproof.adapters.demo_identity import DemoIdentity
from caseproof.adapters.http_outbound import export
from caseproof.adapters.sqlite_casestore import ConflictError
from caseproof.config import Settings
from caseproof.domain.actions import correct, request_state
from caseproof.domain.evidence import diff
from caseproof.domain.review import approve
from caseproof.pipeline.orchestrator import Orchestrator
from caseproof.worker import run_one


class CreateCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_account: str
    reported_at: str
    first_contact: str | None = None


class Followup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    expected_version: int = Field(ge=0)
    owner: str = Field(min_length=1, max_length=120)
    state: Literal["open", "awaiting_external"] = "open"
    next_action: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    due_at: str | None = None


class Correction(BaseModel):
    value: Any
    reason: str
    expected_revision: int


class ReferralReview(BaseModel):
    expected_revision: int
    digest: str
    reason: str


class DemoSession(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,24}$")


class Review(BaseModel):
    disposition: Literal["COMPLETE_HANDOFF", "ESCALATE_WITH_GAPS"]
    expected_revision: int
    digest: str
    reason: str


class RequestResponse(BaseModel):
    state: Literal["fulfilled", "unavailable", "skipped"]
    reason: str = ""
    expected_revision: int


class CustomerReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str = ""
    unavailable: bool = False


class NetworkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    network_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    seed: int = Field(default=35, ge=0, le=10000)


class BankUnavailable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


def create_app(settings=None):
    settings = settings or Settings()
    if settings.runtime_backend == "google":
        from caseproof.cloud.app import create_app as create_cloud_app

        return create_cloud_app(settings)
    o = Orchestrator(settings)
    app = FastAPI(title="CaseProof local synthetic case workspace")
    app.state.orchestrator = o
    from caseproof.adapters.customer_links import CustomerLinks

    links = CustomerLinks(o)
    from caseproof.api.victim import install

    install(app, o)

    @app.middleware("http")
    async def safe_error_boundary(request, call_next):
        try:
            response = await call_next(request)
            if request.url.path.startswith("/v1/victim/"):
                response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Operation failed; inspect job state or retry",
                    "error_type": type(error).__name__,
                },
            )

    def identity(x_demo_user: str = Header(default="analyst")):
        if not settings.demo_mode:
            raise HTTPException(
                403, "demo identity disabled; configure a production identity adapter"
            )
        try:
            return DemoIdentity().actor(x_demo_user)
        except PermissionError:
            raise HTTPException(403, "unknown demo identity") from None

    def authorised(case_id, actor):
        if o.store.metadata(case_id)["tenant_id"] != actor.tenant_id:
            raise PermissionError("tenant mismatch")

    def mutation(actor):
        if actor.role not in ("analyst", "admin"):
            raise PermissionError("analyst role required")

    @app.exception_handler(ConflictError)
    async def conflict_handler(request, error):
        return JSONResponse(status_code=409, content={"error": str(error)})

    @app.exception_handler(PermissionError)
    async def permission_handler(request, error):
        return JSONResponse(status_code=403, content={"error": "role or tenant access denied"})

    @app.exception_handler(KeyError)
    async def missing_handler(request, error):
        return JSONResponse(status_code=404, content={"error": "resource not found"})

    @app.exception_handler(ValueError)
    async def value_handler(request, error):
        if str(error).startswith("stale_bank_data:"):
            return JSONResponse(
                status_code=422,
                content={"error": "stale_bank_data: refresh bank observations and reprocess"},
            )
        return JSONResponse(
            status_code=422,
            content={"error": "invalid action or evidence", "error_type": type(error).__name__},
        )

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "service": "caseproof-api",
            "synthetic": True,
            "mode": o.llm.mode,
            "provider": o.llm.provider,
            "model": o.llm.model_id,
            "adapters": ["filesystem", "SQLite", "DuckDB", "demo identity", "synthetic HTTP"],
            "case_count": len(o.store.list_cases()),
            "external_worker": settings.external_worker,
            "customer_portal": settings.customer_portal,
        }

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/inspector")

    @app.get("/v1/workspace")
    def workspace_summary(
        request: Request, scope: Literal["all", "active"] = "all", actor=Depends(identity)
    ):
        from caseproof.api.workspace import workspace

        accounts = None
        if scope == "active" and settings.preloaded_demo:
            accounts = [p["account"] for p in app.state.demo_catalogue(request)["customers"]]
        return workspace(o.store, actor.tenant_id, accounts=accounts)

    @app.get("/v1/cases/{case_id}/workflow")
    def case_workflow(case_id: str, actor=Depends(identity)):
        from caseproof.api.workspace import workspace

        authorised(case_id, actor)
        return next(
            r
            for r in workspace(o.store, actor.tenant_id, case_id)["cases"]
            if r["case_id"] == case_id
        )

    @app.get("/v1/cases/{case_id}/brief")
    def investigation_brief(case_id: str, actor=Depends(identity)):
        from caseproof.api.workspace import workspace
        from caseproof.domain.brief import readable_brief

        authorised(case_id, actor)
        brief = workspace(o.store, actor.tenant_id, case_id)["cases"][0]["brief"]
        return Response(
            readable_brief(brief),
            media_type="text/plain",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/v1/cases/{cid}/genai/summary")
    def genai_summary(cid: str, revision: int | None = None, actor=Depends(identity)):
        from sqlalchemy import text

        from caseproof.domain.brief import build_brief
        from caseproof.domain.contracts import Approval
        from caseproof.genai import case_summary

        authorised(cid, actor)
        snap = o.store.get(cid, revision)
        with o.store.engine.connect() as db:
            row = db.execute(
                text("SELECT data FROM approvals WHERE case_id=:c AND revision=:r"),
                {"c": cid, "r": snap.revision},
            ).first()
        approval = Approval.model_validate_json(row[0]) if row else None
        if approval and approval.digest != snap.digest:
            approval = None
        return case_summary(o, snap, build_brief(snap, approval))

    @app.post("/v1/cases/{cid}/genai/investigate")
    def genai_investigate(cid: str, actor=Depends(identity)):
        from caseproof.adapters.bank_factory import bank_services
        from caseproof.genai import investigate

        authorised(cid, actor)
        snap, meta = o.store.get(cid), o.store.metadata(cid)
        bank = bank_services(o, meta["tenant_id"])[0]
        bank.exclude_case_id = cid
        if snap.clock:
            bank.observation_as_of = snap.clock.as_of
        return investigate(
            o, snap, bank, meta.get("customer_account", ""), meta.get("reported_at", "")
        )

    @app.get("/v1/cases/{cid}/artifacts/{aid}/genai-read")
    def genai_read(cid: str, aid: str, actor=Depends(identity)):
        from caseproof.genai import read_evidence

        authorised(cid, actor)
        snap = o.store.get(cid)
        item = next((a for a in snap.artifacts if a.artifact_id == aid), None)
        if not item:
            raise KeyError("artifact not found")
        if not item.mime_type.startswith("image/"):
            return {"available": False, "reason": "not_an_image"}
        return read_evidence(o, snap, item, o.storage.read(item.object_key))

    @app.post("/v1/cases/{case_id}/followup")
    def followup(case_id: str, body: Followup, actor=Depends(identity)):
        from datetime import datetime

        from caseproof.domain.ownership import assign

        authorised(case_id, actor)
        if body.due_at:
            if datetime.fromisoformat(body.due_at).tzinfo is None:
                raise ValueError("timezone required")
        return assign(o.store, case_id, actor, body)

    @app.get("/inspector")
    def inspector():
        return FileResponse(
            Path(__file__).resolve().parents[1] / "inspector/index.html",
            headers={
                ("Content-Security-Policy"): (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'u"
                    "nsafe-inline'; img-src 'self' blob:; connect-src 'self'; f"
                    "rame-ancestors 'none'"
                )
            },
        )

    @app.get("/inspector.js")
    def inspector_js():
        return FileResponse(
            Path(__file__).resolve().parents[1] / "inspector/inspector.js",
            media_type="application/javascript; charset=utf-8",
        )

    @app.get("/inspector.css")
    def inspector_css():
        return FileResponse(
            Path(__file__).resolve().parents[1] / "inspector/inspector.css", media_type="text/css"
        )

    @app.get("/v1/cases")
    def cases(actor=Depends(identity)):
        return o.store.list_cases(actor.tenant_id)

    @app.get("/v1/queue")
    def queue(actor=Depends(identity)):
        from caseproof.api.workspace import workspace

        return workspace(o.store, actor.tenant_id)["cases"]

    @app.post("/v1/cases")
    def create(body: CreateCase, actor=Depends(identity)):
        mutation(actor)
        meta = body.model_dump()
        meta["first_contact"] = meta["first_contact"] or meta["reported_at"]
        from caseproof.domain.ledger import dt

        dt(meta["reported_at"])
        dt(meta["first_contact"])
        from caseproof.adapters.bank_ingestion import BankIngestion

        BankIngestion(o).check_account(body.customer_account, actor.tenant_id)
        return o.store.create(tenant_id=actor.tenant_id, **meta)

    from caseproof.api.bank_contracts import BankBatch

    @app.post("/v1/bank/imports")
    def bank_import(body: BankBatch, background_tasks: BackgroundTasks, actor=Depends(identity)):
        from caseproof.adapters.bank_ingestion import BankIngestion

        result = BankIngestion(o).ingest(body, actor)
        if result["reprocess_jobs"] and not settings.external_worker:
            for _ in result["reprocess_jobs"]:
                background_tasks.add_task(run_one, o.jobs, o)
        return result

    @app.get("/v1/bank/customers")
    def bank_customers(actor=Depends(identity)):
        from caseproof.adapters.bank_ingestion import BankIngestion

        return BankIngestion(o).customers(actor.tenant_id)

    @app.get("/simulator")
    def bank_simulator():
        return FileResponse(Path(__file__).resolve().parents[1] / "inspector/simulator.html")

    @app.post("/v1/local/demo-sessions")
    def fresh_demo_session(body: DemoSession, actor=Depends(identity)):
        from local_services.demo_world import DemoWorld

        return DemoWorld(o).start(body.session_id, actor)

    @app.get("/simulator.js")
    def bank_simulator_js():
        return FileResponse(
            Path(__file__).resolve().parents[1] / "inspector/simulator.js",
            media_type="application/javascript",
        )

    @app.post("/v1/local/bank-network")
    def network_create(body: NetworkRequest, actor=Depends(identity)):
        from local_services.bank_network import BankNetwork

        return BankNetwork(o).create(body.network_id, body.seed, actor)

    @app.get("/v1/local/bank-network/{network_id}/dataset")
    def network_dataset(network_id: str, actor=Depends(identity)):
        from local_services.bank_network import BankNetwork

        return BankNetwork(o).read(network_id, actor)["dataset"]

    @app.get("/v1/local/bank-network/{network_id}/receipt")
    def network_receipt(network_id: str, actor=Depends(identity)):
        from local_services.bank_network import BankNetwork

        return Response(
            BankNetwork(o).receipt(network_id, actor),
            media_type="image/png",
            headers={"Content-Disposition": 'attachment; filename="synthetic-receipt.png"'},
        )

    @app.post("/v1/local/bank-network/{network_id}/reports")
    def network_reports(
        network_id: str, background_tasks: BackgroundTasks, actor=Depends(identity)
    ):
        from local_services.bank_network import BankNetwork

        result = BankNetwork(o).publish_reports(network_id, actor)
        if not settings.external_worker:
            for _ in result["reprocess_jobs"]:
                background_tasks.add_task(run_one, o.jobs, o)
        return result

    @app.post("/v1/local/bank-network/{network_id}/refresh")
    def refresh_bank_network(
        network_id: str, background_tasks: BackgroundTasks, actor=Depends(identity)
    ):
        from local_services.bank_network import BankNetwork

        result = BankNetwork(o).publish_reports(network_id, actor, refresh=True)
        if not settings.external_worker:
            for _ in result["reprocess_jobs"]:
                background_tasks.add_task(run_one, o.jobs, o)
        return result

    @app.post("/v1/local/fixtures/{fixture_id}")
    def local_fixture(fixture_id: str, background_tasks: BackgroundTasks, actor=Depends(identity)):
        import uuid

        from caseproof.domain.clock import clock_state
        from caseproof.domain.ledger import dt
        from caseproof.pipeline.load import load_case

        mutation(actor)
        if settings.llm_provider != "local":
            raise HTTPException(404, "local fixture loading is disabled")
        case_id = fixture_id + "-local-" + uuid.uuid4().hex[:8]
        load_case(o, settings.eval_kit_v3, fixture_id, new_id=case_id)
        snapshot = o.store.get(case_id)
        snapshot.clock = clock_state(
            None, dt(o.store.metadata(case_id)["reported_at"]), replay=True
        )
        old = snapshot.revision
        snapshot.revision += 1
        o.store.publish(snapshot, old, "local_replay_clock")
        job = o.jobs.enqueue(case_id, snapshot.revision)
        if not settings.external_worker:
            background_tasks.add_task(run_one, o.jobs, o)
        return {"case_id": case_id, "job_id": job}

    @app.get("/v1/cases/{case_id}")
    def get_case(case_id: str, actor=Depends(identity)):
        authorised(case_id, actor)
        return o.store.get(case_id)

    @app.post("/v1/cases/{case_id}/bank-verification/unavailable")
    def unavailable_bank(case_id: str, body: BankUnavailable, actor=Depends(identity)):
        from caseproof.domain.actions import bank_unavailable

        authorised(case_id, actor)
        mutation(actor)
        return bank_unavailable(o, case_id, body.reason, body.expected_revision)

    @app.post("/v1/cases/{case_id}/artifacts")
    async def artifacts(
        case_id: str,
        file: UploadFile = File(...),
        kind: str = Form(...),
        stage: str = Form("initial"),
        expected_revision: int | None = Form(None),
        actor=Depends(identity),
    ):
        authorised(case_id, actor)
        mutation(actor)
        data = await file.read(5 * 1024 * 1024 + 1)
        return o.intake.add(case_id, data, file.content_type, kind, stage, expected_revision)

    @app.get("/v1/cases/{case_id}/artifacts/{artifact_id}/content")
    def content(case_id: str, artifact_id: str, actor=Depends(identity)):
        authorised(case_id, actor)
        snap = o.store.get(case_id)
        a = next((a for a in snap.artifacts if a.artifact_id == artifact_id), None)
        if not a:
            raise KeyError("artifact missing")
        return Response(
            o.storage.read(a.object_key),
            media_type=a.mime_type,
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )

    @app.post("/v1/cases/{case_id}/process")
    def process(case_id: str, background_tasks: BackgroundTasks, actor=Depends(identity)):
        authorised(case_id, actor)
        mutation(actor)
        snap = o.store.get(case_id)
        job = o.jobs.enqueue(case_id, snap.revision, priority=10)
        if not settings.external_worker:
            background_tasks.add_task(run_one, o.jobs, o)
        return {"job_id": job, "status": o.jobs.get(job)["status"]}

    @app.get("/v1/jobs/{job_id}")
    def job(job_id: str, actor=Depends(identity)):
        j = o.jobs.get(job_id)
        authorised(j["case_id"], actor)
        return j

    @app.post("/v1/jobs/{job_id}/retry")
    def retry_job(job_id: str, background_tasks: BackgroundTasks, actor=Depends(identity)):
        authorised(o.jobs.get(job_id)["case_id"], actor)
        mutation(actor)
        result = o.jobs.retry(job_id)
        if not settings.external_worker:
            background_tasks.add_task(run_one, o.jobs, o)
        return result

    @app.get("/v1/cases/{case_id}/audit")
    def audit(case_id: str, actor=Depends(identity)):
        from sqlalchemy import text

        authorised(case_id, actor)
        with o.store.engine.connect() as db:
            return [
                dict(r._mapping)
                for r in db.execute(
                    text(
                        "SELECT revision,event,at FROM audit_events WHERE case_id=:id ORDER BY id"
                    ),
                    {"id": case_id},
                )
            ]

    @app.get("/v1/cases/{case_id}/approvals")
    def approval_history(case_id: str, actor=Depends(identity)):
        import json

        from sqlalchemy import text

        authorised(case_id, actor)
        with o.store.engine.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    text("SELECT data FROM approval_history WHERE case_id=:id ORDER BY revision"),
                    {"id": case_id},
                )
            ]

    @app.get("/v1/cases/{case_id}/urgent-referrals")
    def referral_history(case_id: str, actor=Depends(identity)):
        authorised(case_id, actor)
        from caseproof.domain.referral import history

        return history(o.store, case_id)

    @app.get("/v1/cases/{case_id}/delivered-packets/{packet_id}")
    def delivered_packet(case_id: str, packet_id: str, actor=Depends(identity)):
        import json

        from sqlalchemy import text

        authorised(case_id, actor)
        with o.store.engine.connect() as db:
            row = db.execute(
                text(
                    "SELECT payload FROM outbox WHERE case_id=:c AND kind='case_ticket' "
                    "AND status='sent' AND json_extract(payload,'$.packet_id')=:p"
                ),
                {"c": case_id, "p": packet_id},
            ).first()
        if not row:
            raise KeyError("delivered packet missing")
        return json.loads(row[0])

    @app.get("/v1/cases/{case_id}/delivered-packets/{packet_id}/document")
    def handoff_document(case_id: str, packet_id: str, actor=Depends(identity)):
        from caseproof.domain.handoff_document import render_document

        packet = delivered_packet(case_id, packet_id, actor)
        return Response(
            render_document(packet),
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": 'attachment; filename="caseproof-handoff.html"',
            },
        )

    @app.post("/v1/cases/{case_id}/urgent-referrals")
    def referral_approval(case_id: str, body: ReferralReview, actor=Depends(identity)):
        authorised(case_id, actor)
        from caseproof.domain.referral import approve as approve_referral

        return approve_referral(o, case_id, actor, body.expected_revision, body.digest, body.reason)

    @app.post("/v1/cases/{case_id}/urgent-referrals/{approval_id}/send")
    def referral_send(case_id: str, approval_id: str, actor=Depends(identity)):
        authorised(case_id, actor)
        from caseproof.domain.referral import send as send_referral

        return send_referral(o, case_id, approval_id, actor)

    @app.post("/v1/cases/{case_id}/upload-links")
    def upload_link(case_id: str, actor=Depends(identity)):
        authorised(case_id, actor)
        mutation(actor)
        if not settings.customer_portal:
            raise HTTPException(404, "customer portal is disabled")
        return links.issue(case_id)

    @app.get("/customer/{token}")
    def customer_page(token: str):
        status_code = 200
        try:
            links.resolve(token)
        except PermissionError:
            # Keep the denied HTTP status and all API checks; render a useful empty shell.
            status_code = 403
        return FileResponse(
            Path(__file__).resolve().parents[1] / "inspector/customer.html",
            status_code=status_code,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    @app.get("/customer.js")
    def customer_script():
        return FileResponse(Path(__file__).resolve().parents[1] / "inspector/customer.js")

    @app.get("/v1/customer/{token}")
    def customer_info(token: str):
        return links.describe(token)

    @app.post("/v1/customer/{token}/artifacts")
    async def customer_artifact(token: str, file: UploadFile = File(...), kind: str = Form(...)):
        data = await file.read(5 * 1024 * 1024 + 1)
        return links.upload(token, data, file.content_type, kind)

    @app.post("/v1/customer/{token}/complete")
    def customer_complete(token: str, body: CustomerReply, background_tasks: BackgroundTasks):
        result = links.complete(token, body.notes, body.unavailable)
        if not settings.external_worker:
            background_tasks.add_task(run_one, o.jobs, o)
        return result

    @app.get("/v1/cases/{case_id}/revisions/{a}/diff/{b}")
    def revision_diff(case_id: str, a: int, b: int, actor=Depends(identity)):
        authorised(case_id, actor)
        return diff(o.store.get(case_id, a), o.store.get(case_id, b))

    @app.patch("/v1/cases/{case_id}/claims/{claim_id}")
    def correction(case_id: str, claim_id: str, body: Correction, actor=Depends(identity)):
        authorised(case_id, actor)
        mutation(actor)
        return correct(o, case_id, claim_id, body.value, body.reason, body.expected_revision)

    @app.post("/v1/cases/{case_id}/requests/{request_id}/send")
    def send_request(case_id: str, request_id: str, actor=Depends(identity)):
        authorised(case_id, actor)
        mutation(actor)
        if settings.customer_portal:
            result = links.issue(case_id, request_id)
            from sqlalchemy import text

            with o.store.engine.begin() as db:
                db.execute(
                    text("INSERT OR REPLACE INTO victim_inbox VALUES(:c,:r,:u,:e)"),
                    {"c": case_id, "r": request_id, "u": result["url"], "e": result["expires_at"]},
                )
            return result
        # Loopback customer simulator; only its response can release a followup.
        from mock_services.customer import reply

        meta = o.store.metadata(case_id)
        if meta.get("kit_case_id"):
            root = (
                settings.eval_kit_v3
                if (settings.eval_kit_v3 / "inputs" / (meta["kit_case_id"] + ".json")).exists()
                else settings.eval_kit_v2
            )
            if not (root / "inputs" / (meta["kit_case_id"] + ".json")).exists():
                raise HTTPException(
                    422,
                    (
                        "Reply simulator unavailable for this fixture; upload a fol"
                        "lowup artifact and record its response"
                    ),
                )
            return reply(o, root, case_id, request_id)
        return request_state(o, case_id, request_id, "accepted")

    @app.post("/v1/cases/{case_id}/requests/{request_id}/response")
    def respond(case_id: str, request_id: str, body: RequestResponse, actor=Depends(identity)):
        authorised(case_id, actor)
        mutation(actor)
        request_state(o, case_id, request_id, body.state, body.reason, body.expected_revision)
        return o.process(case_id)

    @app.post("/v1/cases/{case_id}/reviews")
    def review(case_id: str, body: Review, actor=Depends(identity)):
        authorised(case_id, actor)
        return approve(
            o.store,
            case_id,
            actor,
            body.expected_revision,
            body.digest,
            body.disposition,
            body.reason,
        )

    @app.get("/v1/ui-config")
    def frontend_config():
        from caseproof.api.ui_views import ui_config

        return ui_config()

    @app.get("/v1/cases/{case_id}/report-preview")
    def report_preview(case_id: str, actor=Depends(identity)):
        authorised(case_id, actor)
        snap = o.store.get(case_id)
        from caseproof.domain.report_update import receipt_debits

        return {
            "revision": snap.revision,
            "digest": snap.digest,
            "requires_approval": True,
            "ledger_debits": [m.model_dump() for m in snap.ledger_matches],
            "unreported": [u.model_dump() for u in snap.unreported],
            "evidence_only_debits": receipt_debits(snap),
            "trail": snap.trail,
            "clock": snap.clock.model_dump() if snap.clock else None,
        }

    @app.post("/v1/cases/{case_id}/exports")
    def export_case(case_id: str, actor=Depends(identity)):
        authorised(case_id, actor)
        if actor.role not in ("reviewer", "admin"):
            raise PermissionError("reviewer role required")
        return export(o, case_id)

    return app


app = create_app()
