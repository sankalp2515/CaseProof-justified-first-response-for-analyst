"""IAM-protected synthetic receiver with durable idempotency; never a real bank."""

import uuid

from fastapi import FastAPI, Header, HTTPException

from caseproof.adapters.firestore_casestore import identity
from caseproof.adapters.firestore_documents import FirestoreDocuments
from caseproof.domain.contracts import canonical, hash_json


def create_app(settings, documents=None):
    docs = (
        documents
        if documents is not None
        else FirestoreDocuments(settings.google_cloud_project, settings.firestore_namespace)
    )
    app = FastAPI(title="CaseProof hosted fictional receiving services")

    @app.get("/health")
    def health():
        return {"ok": True, "synthetic": True, "official_report": False}

    @app.post("/{kind}")
    def receive(kind: str, payload: dict, idempotency_key: str = Header(default="")):
        if kind not in {"cfcfrms_report_update", "case_ticket", "urgent_referral"}:
            raise HTTPException(404, "unknown_action")
        if payload.get("synthetic") is not True or not 1 <= len(idempotency_key) <= 200:
            raise HTTPException(422, "synthetic_payload_and_idempotency_key_required")
        if len(canonical(payload).encode()) > 800_000:
            raise HTTPException(413, "packet_limit")
        digest = hash_json(payload)
        path = "simulator_receipts/" + identity(kind, idempotency_key)

        def receive_once(tx):
            prior = tx.get(path)
            if prior:
                if prior["digest"] != digest:
                    raise HTTPException(409, "idempotency_content_conflict")
                return prior["receipt"]
            receipt = {
                "message_id": "SYNTH-" + uuid.uuid4().hex[:16],
                "kind": kind,
                "status": "received_by_fictional_service",
                "synthetic": True,
                "official_report": False,
            }
            tx.set(path, {"digest": digest, "receipt": receipt}, create=True)
            return receipt

        return docs.transact(receive_once)

    return app
