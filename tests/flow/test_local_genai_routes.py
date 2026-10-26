from tests.flow.test_api import client


def test_local_summary_is_revision_bound_and_tenant_scoped(tmp_path, monkeypatch):
    calls = []

    def summary(o, snap, brief):
        calls.append(snap.revision)
        return {"available": True, "revision": snap.revision}

    monkeypatch.setattr("caseproof.genai.case_summary", summary)
    with client(tmp_path) as c:
        store = c.app.state.orchestrator.store
        snap = store.create("MINE")
        snap.revision = 2
        store.publish(snap, 1)
        store.create("OTHER", tenant_id="other")
        assert c.get("/v1/cases/MINE/genai/summary?revision=1").json()["revision"] == 1
        assert c.get("/v1/cases/MINE/genai/summary").json()["revision"] == 2
        assert c.get("/v1/cases/OTHER/genai/summary").status_code == 403
        assert c.get("/v1/cases/MISSING/genai/summary").status_code == 404
        assert calls == [1, 2]


def test_local_investigation_and_image_routes_enforce_case_access(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("caseproof.genai.investigate", lambda *args: calls.append(args[1].case_id) or {"available": True})
    with client(tmp_path) as c:
        store = c.app.state.orchestrator.store
        store.create("MINE", customer_account="A")
        store.create("OTHER", tenant_id="other")
        assert c.post("/v1/cases/OTHER/genai/investigate").status_code == 403
        assert c.post("/v1/cases/MINE/genai/investigate").status_code == 200
        assert calls == ["MINE"]
        assert c.get("/v1/cases/OTHER/artifacts/absent/genai-read").status_code == 403
        assert c.get("/v1/cases/MINE/artifacts/absent/genai-read").status_code == 404
