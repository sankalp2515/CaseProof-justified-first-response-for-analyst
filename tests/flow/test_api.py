from fastapi.testclient import TestClient

from caseproof.api.app import create_app
from caseproof.config import Settings


def client(tmp_path):
    s = Settings(
        _env_file=None,
        llm_mode="mock",
        data_dir=tmp_path,
        object_dir=tmp_path / "objects",
        sqlite_url="sqlite:///" + str(tmp_path / "db.sqlite"),
        duckdb_path=str(tmp_path / "bank.duckdb"),
    )
    return TestClient(create_app(s))


def test_api_intake_process_and_authorised_bytes(tmp_path):
    with client(tmp_path) as c:
        assert c.get("/health").status_code == 200
        case = c.post(
            "/v1/cases", json={"customer_account": "A", "reported_at": "2026-10-01T12:00:00+05:30"}
        ).json()["case_id"]
        s = c.post(
            f"/v1/cases/{case}/artifacts",
            files={
                "file": (
                    "story.txt",
                    b"Caller claimed bank officer and asked safe account transfer.",
                    "text/plain",
                )
            },
            data={"kind": "narrative"},
        ).json()
        aid = s["artifacts"][0]["artifact_id"]
        assert c.get(f"/v1/cases/{case}/artifacts/{aid}/content").status_code == 200
        assert c.get(f"/v1/cases/{case}", headers={"X-Demo-User": "intruder"}).status_code == 403
        job = c.post(f"/v1/cases/{case}/process").json()["job_id"]
        assert c.get(f"/v1/jobs/{job}").json()["status"] == "done"
        assert c.get("/inspector").status_code == 200
        assert (
            c.post(
                f"/v1/cases/{case}/reviews",
                json={
                    "expected_revision": 1,
                    "digest": "stale",
                    "disposition": "COMPLETE_HANDOFF",
                    "reason": "review",
                },
                headers={"X-Demo-User": "reviewer"},
            ).status_code
            == 409
        )
        assert (
            c.post(
                f"/v1/cases/{case}/reviews",
                json={
                    "expected_revision": 1,
                    "digest": "stale",
                    "disposition": "COMPLETE_HANDOFF",
                    "reason": "review",
                },
            ).status_code
            == 403
        )
