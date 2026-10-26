"""Full cloud-adapter workflow with explicit service doubles, not live Google/OCR quality."""

import copy
import json
import time
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from caseproof.adapters.cloud_bank_ingestion import CloudBankIngestion
from caseproof.adapters.firestore_casestore import FirestoreCaseStore, identity
from caseproof.adapters.firestore_jobs import FirestoreJobs
from caseproof.adapters.firestore_llm_cache import FirestoreLLMCache
from caseproof.adapters.gcs_storage import GCSStorage
from caseproof.adapters.literal_extractor import LiteralExtractor
from caseproof.adapters.provider import Provider
from caseproof.adapters.quarantine_storage import QuarantineStorage
from caseproof.cloud.app import create_app
from caseproof.cloud.bank_network import CloudBankNetwork
from caseproof.cloud.runtime import process_job
from caseproof.cloud.simulator import create_app as simulator_app
from caseproof.config import Settings
from caseproof.domain.contracts import Actor, Segment
from caseproof.domain.ledger import dt
from caseproof.pipeline.ingest import Intake
from caseproof.pipeline.orchestrator import Orchestrator
from tests.unit.test_document_ai import Service as OCRService
from tests.unit.test_firestore_state import Documents
from tests.unit.test_gcs_storage import ObjectService


def cloud_settings(tmp_path):
    return Settings(
        _env_file=None,
        runtime_backend="google",
        data_dir=tmp_path,
        llm_provider="vertex",
        llm_mode="live",
        gemini_model="test-model",
        google_cloud_project="caseproof-test",
        google_cloud_location="asia-south1",
        storage_backend="gcs",
        gcs_bucket="clean-caseproof",
        gcs_quarantine_bucket="quarantine-caseproof",
        ocr_provider="documentai",
        documentai_processor_id="test",
        documentai_processor_version="test-v1",
        firestore_namespace="offline",
        external_worker=True,
        customer_portal=True,
        cloud_worker_url="https://worker.run.app",
        cloud_simulator_url="https://simulator.run.app",
        cloud_scanner_url="https://scanner.run.app",
        public_base_url="https://caseproof.test",
        cloud_tasks_account="tasks@caseproof-test.iam.gserviceaccount.com",
        cloud_scheduler_account="scheduler@caseproof-test.iam.gserviceaccount.com",
    )


class AnalyticalService:
    """Only a semantic service double. Production SQL syntax is tested separately."""

    def __init__(self):
        self.tables = {k: {} for k in ("bank_batches", "downstream_reports", "complaints")}

    def table(self, name):
        return name

    def publish(self, table, tenant, record_id, digest, payload):
        old = self.tables[table].get((tenant, record_id))
        if old:
            assert old["digest"] == digest
        self.tables[table][tenant, record_id] = {"digest": digest, "payload": json.loads(payload)}

    def query(self, sql, params):
        table = next(t for t in self.tables if t in sql)
        values = [
            copy.deepcopy(v["payload"])
            for (tenant, _), v in self.tables[table].items()
            if tenant == params["tenant"]
        ]
        if "$.transactions" in sql:
            rows = {}
            for batch in values:
                for t in batch["transactions"]:
                    if t["account"] == params["account"] and dt(t["ts"]) <= dt(params["as_of"]):
                        rows[t["txn_id"]] = {
                            k: t[k]
                            for k in (
                                "txn_id",
                                "account",
                                "amount_minor",
                                "payee",
                                "ts",
                                "reference",
                                "direction",
                            )
                        }
            return list(rows.values())
        if table == "complaints":
            latest = {}
            for row in values:
                latest[row["complaint_id"]] = row
            return list(latest.values())
        if table == "downstream_reports":
            values = [r for r in values if dt(r["reported_at"]) <= dt(params["as_of"])]
        return values


class Tasks:
    def __init__(self):
        self.commands = []

    def publish(self, intent):
        self.commands.append(copy.deepcopy(intent))
        return "projects/test/tasks/" + intent["key"] + "-" + str(intent["generation"])

    def drain(self, o, receiver):
        from caseproof.adapters.cloud_tasks import publish_pending
        from caseproof.cloud.outbound import dispatch

        for _ in range(50):
            publish_pending(o.store.documents, self)
            if not self.commands:
                return
            intent = self.commands.pop(0)
            kind, resource = intent["kind"], intent["resource_id"]
            if kind == "scan":
                o.storage.scan(resource)
            elif kind == "bank_publish":
                o.bank_ingestion.publish(resource)
            elif kind == "process":
                process_job(o, resource)
            elif kind == "outbound":
                dispatch(o, resource, service=receiver)
        raise AssertionError("cloud contract queue did not drain")


def runtime(tmp_path, monkeypatch):
    settings = cloud_settings(tmp_path)
    docs = Documents()
    o = Orchestrator.__new__(Orchestrator)
    o.s, o.store, o.bigquery, o.fixtures = (
        settings,
        FirestoreCaseStore(docs),
        AnalyticalService(),
        {},
    )
    o.jobs = FirestoreJobs(o.store)
    o.bank_ingestion = CloudBankIngestion(o.store, o.bigquery)
    clean, quarantine = ObjectService(), ObjectService()
    scanner = SimpleNamespace(
        post=lambda path, **kw: {
            "status": "clean",
            "sha256": sha256(kw["content"]).hexdigest(),
            "engine": "contract-test",
            "signatures_at": time.time(),
        }
    )
    o.storage = QuarantineStorage(
        GCSStorage(settings.gcs_quarantine_bucket, session=quarantine),
        GCSStorage(settings.gcs_bucket, session=clean),
        docs,
        scanner,
    )
    o.intake = Intake(o.storage, o.store)

    def generate(**kwargs):
        inputs = json.loads(kwargs["contents"][1])
        segments = [Segment.model_validate(s) for s in inputs["segments"]]
        result = LiteralExtractor().extract_claims("test", 1, segments)
        return SimpleNamespace(
            text=json.dumps(
                {"claims": [c.model_dump() for c in result.claims], "unresolved_fields": []}
            ),
            usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=10),
        )

    monkeypatch.setattr(
        "caseproof.adapters.provider.client",
        lambda s: SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )
    o.llm = Provider(settings, cache=FirestoreLLMCache(settings, docs))
    tasks = Tasks()
    monkeypatch.setattr("caseproof.cloud.app.CloudTasks", lambda *args, **kw: tasks)
    monkeypatch.setattr(
        "caseproof.cloud.app.staff",
        lambda s, authorization: Actor(
            user_id=authorization or "missing",
            role="reviewer" if authorization == "Bearer reviewer" else "analyst",
            tenant_id="demo",
        ),
    )
    simulator = TestClient(simulator_app(settings, docs), base_url="https://simulator.test")

    def send(path, **kwargs):
        result = simulator.post(
            path, json=kwargs["json"], headers={"Idempotency-Key": kwargs["key"]}
        )
        result.raise_for_status()
        return result.json()

    receiver = SimpleNamespace(post=send)
    return o, tasks, receiver, clean


def receipt_and_ocr(tx):
    lines = [f"INR {tx['amount_minor'] / 100:.2f}", tx["ts"], "To: " + tx["payee"]]
    image = Image.new("RGB", (1100, 300), "white")
    draw = ImageDraw.Draw(image)
    for i, text in enumerate(lines):
        draw.text((20, i * 80 + 20), text, fill="black")
    output = BytesIO()
    image.save(output, format="PNG")
    text, layouts = "", []
    for i, line in enumerate(lines):
        start = len(text)
        text += line + "\n"
        layouts.append(
            {
                "layout": {
                    "confidence": 0.99,
                    "textAnchor": {
                        "textSegments": [{"startIndex": str(start), "endIndex": str(len(text))}]
                    },
                    "boundingPoly": {
                        "normalizedVertices": [
                            {"x": 0.01, "y": i * 0.3 + 0.01},
                            {"x": 0.99, "y": i * 0.3 + 0.01},
                            {"x": 0.99, "y": i * 0.3 + 0.25},
                            {"x": 0.01, "y": i * 0.3 + 0.25},
                        ]
                    },
                }
            }
        )
    return output.getvalue(), {
        "document": {"text": text, "pages": [{"pageNumber": 1, "lines": layouts}]}
    }


def test_new_cloud_complaint_request_reply_approval_and_two_deliveries(tmp_path, monkeypatch):
    o, tasks, receiver, clean = runtime(tmp_path, monkeypatch)
    actor = Actor(user_id="bank-simulator", role="admin", tenant_id="demo")
    world = CloudBankNetwork(o).seed_tenant(actor)
    from local_services.demo_world import NAMES

    assert [c["display_name"] for c in world["customers"]] == [
        name + " (synthetic)" for name in NAMES
    ]
    o.store.documents.transact(
        lambda tx: tx.set(
            "demo_catalogues/" + identity("demo"), {"tenant": "demo", "catalogue": world}
        )
    )
    tasks.drain(o, receiver)
    assert o.store.list_cases() == []
    with TestClient(create_app(o.s, o), base_url="https://caseproof.test") as client:
        account = world["customers"][0]
        assert (
            client.post("/v1/victim/sessions", json={"customer_id": account["account"]}).status_code
            == 200
        )
        me = client.get("/v1/victim/me").json()
        t1 = next(t for t in me["transactions"] if t["txn_id"].endswith("-T1"))
        body = {
            "submission_id": "brand-new-cloud-complaint",
            "narrative": "The caller told me to transfer money to a safe account.",
            "transaction_ids": [t1["txn_id"]],
            "payment_authorisation": "deceived",
        }
        created = client.post("/v1/victim/complaints", json=body)
        assert created.status_code == 200, created.text
        cid = created.json()["case_id"]
        assert client.post("/v1/victim/complaints", json=body).json()["case_id"] == cid
        image, response = receipt_and_ocr(t1)
        monkeypatch.setattr(
            "caseproof.adapters.document_ai.authorized_session", lambda: OCRService(response)
        )
        uploaded = client.post(
            f"/v1/victim/complaints/{cid}/artifacts",
            data={"kind": "receipt"},
            files={"file": ("receipt.png", image, "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text
        original = o.store.get(cid)
        tasks.drain(o, receiver)
        snapshot = o.store.get(cid)
        assert snapshot.ledger_matches and snapshot.unreported
        assert (
            client.get("/v1/workspace?scope=active").json()["cases"][0][
                "selected_bank_amount_minor"
            ]
            == t1["amount_minor"]
        )
        assert any(r.provider == "documentai" for r in snapshot.run_meta)
        assert all(r.mode == "live" for r in snapshot.run_meta)  # Service doubles, not live Google!
        rid = next(r.request_id for r in snapshot.requests if r.state == "proposed")
        issued = client.post(
            f"/v1/cases/{cid}/requests/{rid}/send", headers={"Authorization": "Bearer analyst"}
        )
        assert issued.status_code == 200, issued.text
        token = issued.json()["url"].rsplit("/", 1)[1]
        t2 = snapshot.unreported[0]
        note = (
            f"I also paid INR {t2.amount_minor / 100:.2f} on {t2.ts} to {t2.payee}. "
            "The caller told me to transfer money to a safe account."
        )
        completed = client.post(f"/v1/customer/{token}/complete", json={"notes": note})
        assert completed.status_code == 200, completed.text
        tasks.drain(o, receiver)
        CloudBankNetwork(o).publish_reports(account["network_id"], actor, refresh=True)
        tasks.drain(o, receiver)
        snap = o.store.get(cid)
        assert len(snap.ledger_matches) == 2 and not snap.unreported
        assert snap.readiness.disposition == "COMPLETE_CANDIDATE", snap.readiness
        review = {
            "expected_revision": snap.revision,
            "digest": snap.digest,
            "disposition": "COMPLETE_HANDOFF",
            "reason": "Reviewed cited evidence and independent bank records",
        }
        assert (
            client.post(
                f"/v1/cases/{cid}/reviews", json=review, headers={"Authorization": "Bearer analyst"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/v1/cases/{cid}/reviews",
                json=review,
                headers={"Authorization": "Bearer reviewer"},
            ).status_code
            == 200
        )
        sent = client.post(f"/v1/cases/{cid}/exports", headers={"Authorization": "Bearer reviewer"})
        assert sent.status_code == 200, sent.text
        tasks.drain(o, receiver)
        rows = o.store.documents.query("outbox", [("case_id", cid)])
        assert len(rows) == 2 and all(r["status"] == "sent" for r in rows)
        assert (
            client.post(
                f"/v1/cases/{cid}/exports", headers={"Authorization": "Bearer reviewer"}
            ).status_code
            == 200
        )
        tasks.drain(o, receiver)
        assert len(o.store.documents.query("simulator_receipts")) == 2
        assert o.store.get(cid, original.revision).digest == original.digest
        assert any(key.startswith("packets/") for key in clean.objects)
        workflow = client.get(
            f"/v1/cases/{cid}/workflow", headers={"Authorization": "Bearer analyst"}
        )
        assert workflow.status_code == 200, workflow.text
        assert workflow.json()["followup"]["state"] == "awaiting_external"


def test_practice_personas_are_confined_to_the_callers_own_practice_tenant(tmp_path, monkeypatch):
    o, tasks, receiver, clean = runtime(tmp_path, monkeypatch)
    o.s.cloud_practice_personas = True
    o.store.create("SHARED-CASE", tenant_id="demo", customer_account="shared")
    with TestClient(create_app(o.s, o), base_url="https://caseproof.test") as visitor:
        # No practice session cookie: a persona header grants nothing.
        denied = visitor.get("/v1/workspace?scope=all", headers={"X-Demo-User": "analyst"})
        assert denied.status_code == 401
        assert denied.json()["detail"] == "practice_session_required"
        # First visit: an empty customer list, not an error.
        assert visitor.get("/v1/victim/demo-customers").json()["customers"] == []
        made = visitor.post("/v1/victim/demo-session")
        assert made.status_code == 200, made.text
        tenant = made.json()["session_id"]
        queue = visitor.get("/v1/workspace?scope=all", headers={"X-Demo-User": "analyst"})
        assert queue.status_code == 200, queue.text
        assert all(c["case_id"] != "SHARED-CASE" for c in queue.json()["cases"])
        # Administrative and unknown personas stay unavailable without sign-in.
        for persona in ("admin", "superuser"):
            response = visitor.get("/v1/workspace?scope=all", headers={"X-Demo-User": persona})
            assert response.status_code == 403
        assert (
            visitor.post(
                "/v1/admin/synthetic/preload", headers={"X-Demo-User": "reviewer"}
            ).status_code
            == 403
        )
        shared = visitor.get("/v1/cases/SHARED-CASE", headers={"X-Demo-User": "reviewer"})
        assert shared.status_code in (403, 404)
        assert tenant.startswith("judge-")


def test_practice_session_daily_cap_is_configurable(tmp_path, monkeypatch):
    o, tasks, receiver, clean = runtime(tmp_path, monkeypatch)
    o.s.cloud_practice_daily_limit = 2
    with TestClient(create_app(o.s, o), base_url="https://caseproof.test") as visitor:
        codes = [visitor.post("/v1/victim/demo-session").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_cloud_practice_sessions_are_fresh_named_and_timed(tmp_path, monkeypatch):
    o, tasks, receiver, clean = runtime(tmp_path, monkeypatch)
    with TestClient(create_app(o.s, o), base_url="https://caseproof.test") as visitor:
        assert visitor.post("/v1/victim/demo-session", json={"minutes_ago": 90}).status_code == 200
        first = visitor.get("/v1/victim/demo-customers").json()["customers"]
        assert visitor.post("/v1/victim/demo-session", json={"minutes_ago": 90}).status_code == 200
        second = visitor.get("/v1/victim/demo-customers").json()["customers"]
    names = [c["display_name"] for c in first]
    assert len(set(names)) == len(names) and "Maya Synthetic" not in names
    victims = [c for c in first if c.get("incident")]
    assert len(victims) == 6 and all(c["incident"]["minutes_ago"] == 90 for c in victims)
    amounts = lambda cs: [c["incident"]["amount_minor"] for c in cs if c.get("incident")]  # noqa: E731
    assert amounts(first) != amounts(second) or [c["account"] for c in first] != [
        c["account"] for c in second
    ]
