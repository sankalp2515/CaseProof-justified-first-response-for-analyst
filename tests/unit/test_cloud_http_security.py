"""Actual ASGI routes with fake signature verification and isolated durable stores."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from caseproof.adapters.firestore_casestore import FirestoreCaseStore
from caseproof.cloud import auth
from caseproof.cloud.app import create_app
from caseproof.cloud.body_limit import BodyLimit
from tests.flow.test_google_backend_contract import cloud_settings
from tests.unit.test_firestore_state import Documents


def application(tmp_path, monkeypatch, *, worker=False):
    settings = cloud_settings(tmp_path)
    settings.cloud_staff_audience = "offline-oauth-client"
    settings.cloud_staff_principals = {"staff-A": {"role": "analyst", "tenant_id": "BANK-A"}}
    store = FirestoreCaseStore(Documents())
    store.create("OTHER-BANK", tenant_id="BANK-B")
    calls = []
    o = SimpleNamespace(
        s=settings,
        store=store,
        storage=SimpleNamespace(scan=lambda digest: calls.append(digest) or {"status": "clean"}),
    )

    def verify(token, transport, audience):
        assert audience == (settings.cloud_worker_url if worker else settings.cloud_staff_audience)
        if token == "invalid":
            raise ValueError("invalid token")
        return {
            "sub": "staff-A",
            "email_verified": True,
            "role": "admin",
            "email": settings.cloud_tasks_account
            if token == "tasks"
            else settings.cloud_scheduler_account,
        }

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", verify)
    monkeypatch.setattr(
        "caseproof.cloud.app.CloudTasks",
        lambda *a, **kw: SimpleNamespace(publish=lambda intent: "offline-task"),
    )
    return TestClient(
        create_app(settings, o, worker=worker), base_url="https://caseproof.test"
    ), calls


def test_cloud_staff_route_ignores_demo_headers_and_rejects_cross_tenant(tmp_path, monkeypatch):
    client, _ = application(tmp_path, monkeypatch)
    assert client.get("/v1/workspace", headers={"X-Demo-User": "admin"}).status_code == 403
    assert (
        client.get("/v1/workspace", headers={"Authorization": "Bearer invalid"}).status_code == 403
    )
    assert (
        client.get("/v1/cases/OTHER-BANK", headers={"Authorization": "Bearer staff"}).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/admin/synthetic/preload", headers={"Authorization": "Bearer staff"}
        ).status_code
        == 403
    )


def test_private_worker_requires_exact_tasks_identity(tmp_path, monkeypatch):
    client, calls = application(tmp_path, monkeypatch, worker=True)
    body = {"resource_id": "a" * 64}
    assert client.post("/internal/tasks/scan", json=body).status_code == 403
    assert (
        client.post(
            "/internal/tasks/scan", json=body, headers={"Authorization": "Bearer scheduler"}
        ).status_code
        == 403
    )
    assert calls == []
    assert (
        client.post(
            "/internal/tasks/scan", json=body, headers={"Authorization": "Bearer tasks"}
        ).status_code
        == 200
    )
    assert calls == [body["resource_id"]]


def test_capability_and_authorization_tokens_are_absent_from_request_logs(
    tmp_path, monkeypatch, capsys
):
    client, _ = application(tmp_path, monkeypatch)
    capability = "sensitive-capability-" + "z" * 23
    bearer = "never-log-this-bearer"
    assert (
        client.get(
            "/v1/customer/" + capability, headers={"Authorization": "Bearer " + bearer}
        ).status_code
        == 403
    )
    logged = capsys.readouterr().out
    assert capability not in logged and bearer not in logged
    assert "/v1/customer/{token}" in logged


@pytest.mark.parametrize("length", [b"not-a-number", b"-1", b"1,2"])
def test_invalid_content_length_is_a_client_error(length):
    sent = []

    async def downstream(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(
        BodyLimit(downstream)(
            {"type": "http", "headers": [(b"content-length", length)]}, receive, send
        )
    )
    assert sent[0]["status"] == 400


def test_chunked_body_limit_is_enforced_without_content_length():
    sent = []
    chunks = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )

    async def downstream(scope, receive, send):
        while (await receive()).get("more_body"):
            pass
        pytest.fail("oversized body reached handler")

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    asyncio.run(BodyLimit(downstream, maximum=5)({"type": "http", "headers": []}, receive, send))
    assert sent[0]["status"] == 413
