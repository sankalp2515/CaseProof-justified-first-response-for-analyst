"""Cloud uploads remain unreadable until a digest-bound clean scan is recorded."""

import time

from caseproof.adapters.object_validation import validate_object_key


class EvidenceNotReady(RuntimeError):
    pass


class QuarantineStorage:
    def __init__(self, quarantine, evidence, documents, scanner):
        self.quarantine, self.evidence, self.documents, self.scanner = (
            quarantine,
            evidence,
            documents,
            scanner,
        )

    def put(self, data, mime_type):
        key, digest = self.quarantine.put(data, mime_type)

        def reserve(tx):
            prior = tx.get("evidence_scans/" + digest)
            if prior and prior["status"] == "infected":
                raise ValueError("evidence_rejected_by_scanner")
            if not prior:
                tx.set(
                    "evidence_scans/" + digest,
                    {
                        "digest": digest,
                        "key": key,
                        "mime": mime_type,
                        "status": "pending",
                        "created_at": time.time(),
                    },
                    create=True,
                )
                task = "SCAN-" + digest
                tx.set(
                    "task_intents/" + task,
                    {
                        "key": task,
                        "kind": "scan",
                        "resource_id": digest,
                        "state": "pending",
                        "generation": 0,
                        "created_at": time.time(),
                    },
                    create=True,
                )

        self.documents.transact(reserve)
        return key, digest

    def read(self, key):
        validate_object_key(key)
        result = self.documents.get("evidence_scans/" + key.split("/")[1])
        if not result or result["status"] != "clean":
            raise EvidenceNotReady("EVIDENCE_SCAN_PENDING_OR_REJECTED")
        return self.evidence.read(key)

    def scan(self, digest):
        validate_object_key(digest[:2] + "/" + digest)
        path = "evidence_scans/" + digest
        item = self.documents.get(path)
        if not item:
            raise KeyError("scan intent missing")
        if item["status"] in {"clean", "infected"}:
            return {"status": item["status"], "duplicate": True}
        data = self.quarantine.read(item["key"])
        result = self.scanner.post("/scan", content=data, mime=item["mime"])
        if (
            result.get("sha256") != digest
            or result.get("status") not in {"clean", "infected"}
            or not result.get("engine")
            or not result.get("signatures_at")
            or not time.time() - 72 * 3600 <= result["signatures_at"] <= time.time() + 300
        ):
            raise ValueError("invalid_scan_attestation")
        if result["status"] == "clean":
            promoted, promoted_digest = self.evidence.put(data, item["mime"])
            if promoted != item["key"] or promoted_digest != digest:
                raise ValueError("scan_promotion_digest_mismatch")

        def record(tx):
            old = tx.get(path)
            if old["status"] == "pending":
                old.update(status=result["status"], attestation=result, scanned_at=time.time())
                tx.set(path, old)

        self.documents.transact(record)
        return {"status": result["status"], "duplicate": False}
