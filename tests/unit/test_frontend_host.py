from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from caseproof.api.frontend import integrate_frontend


def application(tmp_path, monkeypatch, valid=True):
    (tmp_path / "index.html").write_text("<html>CaseProof application</html>")
    api = FastAPI()
    api.state.orchestrator = object()

    @api.get("/v1/probe")
    def probe():
        return {"ok": True}

    def resolve(token):
        if not valid:
            raise PermissionError("expired")

    monkeypatch.setattr(
        "caseproof.api.frontend.CustomerLinks", lambda _: SimpleNamespace(resolve=resolve)
    )
    return TestClient(integrate_frontend(api, tmp_path))


def test_frontend_and_api_remain_separate(tmp_path, monkeypatch):
    client = application(tmp_path, monkeypatch)
    assert client.get("/", follow_redirects=False).headers["location"] == "/app/#/entry"
    assert "CaseProof application" in client.get("/app/").text
    assert client.get("/v1/probe").json() == {"ok": True}
    assert client.get("/v1/missing").status_code == 404
    assert client.get("/app/missing.js").status_code == 404
    assert client.get("/v1/probe").headers["cache-control"] == "no-store"


def test_customer_bridge_validates_before_redirect(tmp_path, monkeypatch):
    client = application(tmp_path, monkeypatch)
    response = client.get("/customer/safe-token", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app/#/victim/reply/safe-token"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_integrated_landing_is_the_homepage_when_present(tmp_path, monkeypatch):
    (tmp_path / "landing").mkdir()
    (tmp_path / "landing/index.html").write_text("<html>CaseProof landing</html>")
    client = application(tmp_path, monkeypatch)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "CaseProof landing" in response.text
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_expired_customer_link_stays_denied(tmp_path, monkeypatch):
    client = application(tmp_path, monkeypatch, valid=False)
    assert client.get("/customer/expired").status_code == 403


def test_api_service_runs_without_static_assets(monkeypatch):
    api = FastAPI()
    api.state.orchestrator = object()
    monkeypatch.setattr(
        "caseproof.api.frontend.CustomerLinks",
        lambda _: SimpleNamespace(resolve=lambda token: None),
    )
    client = TestClient(integrate_frontend(api))
    assert client.get("/app/").status_code == 404
    response = client.get("/customer/safe-token", follow_redirects=False)
    assert response.headers["location"] == "/app/#/victim/reply/safe-token"
