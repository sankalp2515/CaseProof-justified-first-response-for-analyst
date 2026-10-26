"""Authenticated explicit commands published from durable Firestore intents."""

import base64
import re
import time
from urllib.parse import urlparse

from caseproof.adapters.google_http import authorized_session
from caseproof.domain.contracts import canonical


class TaskNameRetired(RuntimeError):
    """Tasks retains a completed task name after its body is no longer readable."""


class CloudTasks:
    def __init__(self, project, location, queue, worker_url, caller_email, *, session=None):
        if not all(
            re.fullmatch(r"[a-zA-Z0-9_-]+", part or "") for part in (project, location, queue)
        ):
            raise ValueError("Explicit task project/location/queue required")
        parsed = urlparse(worker_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Explicit HTTPS worker origin required")
        if not re.fullmatch(
            r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com", caller_email or ""
        ):
            raise ValueError("Dedicated Tasks service account required")
        self.parent = f"projects/{project}/locations/{location}/queues/{queue}"
        self.worker, self.caller = worker_url.rstrip("/"), caller_email
        self.session = session if session is not None else authorized_session()

    def publish(self, intent):
        if intent["kind"] not in {"process", "outbound", "bank_publish", "scan"}:
            raise ValueError("Unsupported cloud command")
        task_id = intent["key"] + "-" + str(intent["generation"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,400}", task_id):
            raise ValueError("Invalid task identity")
        name = self.parent + "/tasks/" + task_id
        request = {
            "url": self.worker + "/internal/tasks/" + intent["kind"],
            "httpMethod": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": base64.b64encode(
                canonical({"resource_id": intent["resource_id"]}).encode()
            ).decode(),
            "oidcToken": {"serviceAccountEmail": self.caller, "audience": self.worker},
        }
        response = self.session.post(
            "https://cloudtasks.googleapis.com/v2/" + self.parent + "/tasks",
            json={"task": {"name": name, "httpRequest": request, "dispatchDeadline": "180s"}},
            timeout=20,
        )
        if response.status_code == 409:
            existing = self.session.get(
                "https://cloudtasks.googleapis.com/v2/" + name,
                params={"responseView": "FULL"},
                timeout=20,
            )
            if existing.status_code == 404:
                raise TaskNameRetired(name)
            existing.raise_for_status()
            old = existing.json()["httpRequest"]
            if any(old.get(k) != request[k] for k in ("url", "httpMethod", "body", "oidcToken")):
                raise ValueError("task_identity_content_conflict")
        else:
            response.raise_for_status()
        return name


def publish_pending(documents, client, limit=50):
    sent = 0
    intents = []
    for kind in ("scan", "bank_publish", "outbound", "process"):
        if len(intents) >= limit:
            break
        intents.extend(
            documents.query(
                "task_intents", [("state", "pending"), ("kind", kind)], limit=limit - len(intents)
            )
        )
    for intent in intents:
        try:
            name = client.publish(intent)  # Transport failure keeps the durable intent pending.
        except TaskNameRetired:

            def rotate(tx):
                current = tx.get("task_intents/" + intent["key"])
                if (
                    current
                    and current["generation"] == intent["generation"]
                    and current["state"] == "pending"
                ):
                    if current["generation"] >= 3:
                        current.update(state="failed", error="TASK_NAME_RECOVERY_EXHAUSTED")
                    else:
                        current["generation"] += 1
                    tx.set("task_intents/" + intent["key"], current)

            documents.transact(rotate)
            continue

        def acknowledge(tx):
            current = tx.get("task_intents/" + intent["key"])
            if (
                current
                and current["generation"] == intent["generation"]
                and current["state"] == "pending"
            ):
                current.update(state="published", task_name=name, published_at=time.time())
                tx.set("task_intents/" + intent["key"], current)

        documents.transact(acknowledge)
        sent += 1
    return sent
