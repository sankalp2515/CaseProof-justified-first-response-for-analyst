import hashlib
import time

import pytest
from sqlalchemy import text

from caseproof.adapters.customer_links import CustomerLinks
from caseproof.config import Settings
from caseproof.domain.contracts import EvidenceRequest
from caseproof.pipeline.orchestrator import Orchestrator


def setup(tmp_path):
    settings = Settings(
        _env_file=None,
        llm_provider="mock",
        llm_mode="mock",
        data_dir=tmp_path,
        object_dir=tmp_path / "objects",
        customer_portal=True,
        sqlite_url="sqlite:///" + str(tmp_path / "cases.db"),
        duckdb_path=str(tmp_path / "bank.db"),
    )
    o = Orchestrator(settings)
    o.store.create("A")
    o.store.create("B")
    return o, CustomerLinks(o)


def test_customer_token_hash_expiry_revoke_and_case_scope(tmp_path):
    o, links = setup(tmp_path)
    link = links.issue("A")
    token = link["url"].rsplit("/", 1)[1]
    with o.store.engine.connect() as db:
        stored = db.execute(text("SELECT token_hash FROM customer_links")).scalar_one()
    assert stored == hashlib.sha256(token.encode()).hexdigest() and stored != token
    links.upload(token, b"Customer evidence", "text/plain", "narrative")
    assert len(o.store.get("A").artifacts) == 1 and not o.store.get("B").artifacts
    replacement = links.issue("A")["url"].rsplit("/", 1)[1]
    with pytest.raises(PermissionError):
        links.resolve(token)
    with o.store.engine.begin() as db:
        db.execute(text("UPDATE customer_links SET expires=:expired"), {"expired": time.time() - 1})
    with pytest.raises(PermissionError):
        links.upload(replacement, b"replay", "text/plain", "narrative")


def test_customer_complete_once_and_disabled_portal(tmp_path):
    o, links = setup(tmp_path)
    token = links.issue("A")["url"].rsplit("/", 1)[1]
    result = links.complete(token, "Caller demanded a safe account transfer.")
    assert o.jobs.get(result["job_id"])["status"] == "queued"
    with pytest.raises(PermissionError):
        links.complete(token, "Duplicate reply")
    o.s.customer_portal = False
    with pytest.raises(PermissionError):
        links.resolve(token)


def test_only_one_highest_ranked_request_can_be_sent(tmp_path):
    o, links = setup(tmp_path)
    s = o.store.get("A")
    s.requests = [
        EvidenceRequest(request_id=id, catalogue_id=id, state="proposed")
        for id in ("first", "second")
    ]
    s.revision += 1
    o.store.publish(s, 1)
    with pytest.raises(ValueError, match="highest ranked"):
        links.issue("A", "second")
    links.issue("A", "first")
    with pytest.raises(ValueError, match="outstanding"):
        links.issue("A", "second")
