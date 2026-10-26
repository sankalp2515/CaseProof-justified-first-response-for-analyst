from caseproof.config import Settings
from caseproof.pipeline.orchestrator import Orchestrator
from caseproof.worker import run_one


def test_provider_failure_records_failed_job(tmp_path):
    s = Settings(
        _env_file=None,
        llm_mode="mock",
        data_dir=tmp_path,
        object_dir=tmp_path / "obj",
        sqlite_url="sqlite:///" + str(tmp_path / "db.sqlite"),
    )
    o = Orchestrator(s)
    snap = o.store.create("X", customer_account="A")
    o.llm.mode = "live"
    o.llm.generate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("private"))
    job = o.jobs.enqueue("X", snap.revision)
    run_one(o.jobs, o)
    assert o.jobs.get(job)["status"] == "failed"
    assert o.jobs.get(job)["error"] == "LLM_PROVIDER_ERROR"
    assert o.store.get("X").revision == 1
