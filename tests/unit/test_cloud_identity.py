from types import SimpleNamespace

import pytest

from caseproof.cloud import auth


def test_staff_role_is_server_mapped_and_service_identity_is_exact(monkeypatch):
    settings = SimpleNamespace(
        cloud_staff_audience="staff-client",
        cloud_worker_url="https://worker.run.app",
        cloud_staff_principals={"staff-1": {"role": "analyst", "tenant_id": "bank-A"}},
    )
    token = {
        "sub": "staff-1",
        "email_verified": True,
        "email": "tasks@example.test",
        "role": "admin",
    }
    monkeypatch.setattr(auth, "claims", lambda authorization, audience: token)
    assert auth.staff(settings, "Bearer signed").role == "analyst"
    with pytest.raises(PermissionError):
        auth.service(settings, "Bearer signed", "scheduler@example.test")
    token["email_verified"] = False
    with pytest.raises(PermissionError):
        auth.staff(settings, "Bearer signed")
    token.update(email_verified=True, sub="unassigned")
    with pytest.raises(PermissionError):
        auth.staff(settings, "Bearer signed")


def test_missing_identity_and_invalid_audience_are_rejected(monkeypatch):
    with pytest.raises(PermissionError):
        auth.claims(None, "staff-client")
    with pytest.raises(PermissionError):
        auth.claims("Bearer token", "")

    def invalid(*args, **kwargs):
        assert kwargs["audience"] == "correct-audience"
        raise ValueError("wrong token audience")

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", invalid)
    with pytest.raises(PermissionError):
        auth.claims("Bearer invalid", "correct-audience")
