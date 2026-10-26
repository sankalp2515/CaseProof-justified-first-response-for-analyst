from fastapi.testclient import TestClient

from caseproof.adapters.gcs_storage import GCSStorage
from caseproof.api.app import create_app
from caseproof.config import Settings
from tests.unit.test_gcs_storage import ObjectService


def test_cloud_evidence_intake_read_and_processing_preserve_immutable_revision(
    tmp_path, monkeypatch
):
    service = ObjectService()
    monkeypatch.setattr(
        "caseproof.adapters.storage.GCSStorage",
        lambda bucket: GCSStorage(bucket, session=service),
    )
    settings = Settings(
        _env_file=None,
        llm_provider="local",
        llm_mode="local",
        storage_backend="gcs",
        gcs_bucket="private-caseproof",
        data_dir=tmp_path,
        object_dir=tmp_path / "unused-local-objects",
        sqlite_url="sqlite:///" + str(tmp_path / "case.sqlite"),
        duckdb_path=str(tmp_path / "bank.duckdb"),
    )
    with TestClient(create_app(settings)) as client:
        cid = client.post(
            "/v1/cases",
            json={
                "customer_account": "SYNTH-CLOUD-CUSTOMER",
                "reported_at": "2026-10-15T12:00:00+05:30",
            },
        ).json()["case_id"]
        upload = client.post(
            f"/v1/cases/{cid}/artifacts",
            files={"file": ("story.txt", b"Caller claimed bank officer.", "text/plain")},
            data={"kind": "narrative"},
        )
        assert upload.status_code == 200, upload.text
        before = upload.json()
        aid = before["artifacts"][0]["artifact_id"]
        assert client.get(f"/v1/cases/{cid}/artifacts/{aid}/content").content == (
            b"Caller claimed bank officer."
        )
        process = client.post(f"/v1/cases/{cid}/process")
        assert process.status_code == 200, process.text
        job = client.get("/v1/jobs/" + process.json()["job_id"]).json()
        assert job["status"] == "done", job
        after = client.get(f"/v1/cases/{cid}").json()
        assert after["segments"] and after["revision"] > before["revision"]
        original = client.app.state.orchestrator.store.get(cid, before["revision"])
        assert original.digest == before["digest"]
        assert len(service.objects) == 1
        assert not settings.object_dir.exists()
