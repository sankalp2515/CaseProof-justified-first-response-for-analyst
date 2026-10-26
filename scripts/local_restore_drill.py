"""Cold-copy a quiesced local volume, verify an isolated restore, resume a witness job.

Run only after gateway/API/worker/feed/simulator writers are stopped. This tool
does not stop them itself. Original volume is mounted read-only; writes go only
to the named new output directory and a temporary isolated restore.
"""

import argparse
import json
import shutil
import sqlite3
import tempfile
from hashlib import sha256
from pathlib import Path

import duckdb
from sqlalchemy import text

from caseproof.config import Settings
from caseproof.domain.contracts import CaseSnapshot
from caseproof.pipeline.orchestrator import Orchestrator
from caseproof.worker import run_one


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Do not follow links out of the backup root")
        if path.is_file():
            files[str(path.relative_to(root))] = sha256(path.read_bytes()).hexdigest()
    return files


def inspect(root):
    report = {"sqlite": {}, "snapshots": 0, "artifacts": 0}
    object_hashes = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            header = stream.read(16)
        if header != b"SQLite format 3\x00":
            continue
        with sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True) as db:
            assert db.execute("PRAGMA quick_check").fetchall() == [("ok",)]
            tables = [
                r[0]
                for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            report["sqlite"][str(path.relative_to(root))] = {
                table: db.execute(
                    'SELECT count(*) FROM "' + table.replace('"', '""') + '"'
                ).fetchone()[0]
                for table in tables
            }
            if "snapshots" in tables:
                for cid, revision, digest, data in db.execute(
                    "SELECT case_id,revision,digest,data FROM snapshots"
                ):
                    snap = CaseSnapshot.model_validate_json(data)
                    assert snap.case_id == cid and snap.revision == revision
                    assert snap.digest == digest and snap.valid_digest()
                    report["snapshots"] += 1
                    for artifact in snap.artifacts:
                        path = (root / "objects" / artifact.object_key).resolve()
                        assert path.is_relative_to((root / "objects").resolve())
                        if path not in object_hashes:
                            object_hashes[path] = sha256(path.read_bytes()).hexdigest()
                        assert object_hashes[path] == artifact.sha256
                        report["artifacts"] += 1
    with duckdb.connect(str(root / "bank.duckdb"), read_only=True) as db:
        tables = [r[0] for r in db.execute("SHOW TABLES").fetchall()]
        report["duckdb"] = {
            table: db.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]
            for table in tables
        }
    assert "feed.sqlite" in report["sqlite"] and "mock_outbound.sqlite" in report["sqlite"]
    report["unique_objects_verified"] = len(object_hashes)
    return report


def run(source, output, witness):
    output.mkdir(parents=True, exist_ok=False)
    backup = output / "state"
    before = inventory(source)
    print("Inventoried source", len(before), "files", flush=True)
    shutil.copytree(source, backup)
    assert inventory(backup) == before
    # A read-only mount alone cannot guarantee quiescence, so check original
    # inventory again and fail if any writer was accidentally left running.
    assert inventory(source) == before, "Source changed during cold copy"
    print("Cold copy verified; checking isolated restore", flush=True)
    with tempfile.TemporaryDirectory(prefix="caseproof-restore-") as temporary:
        restored = Path(temporary) / "state"
        shutil.copytree(backup, restored)
        assert inventory(restored) == before
        report = inspect(restored)
        print("Restored snapshots verified", report["snapshots"], flush=True)
        original_inspection = inspect(backup)
        assert report == original_inspection
        o = Orchestrator(
            Settings(
                _env_file=None,
                llm_provider="local",
                external_worker=True,
                data_dir=restored,
                object_dir=restored / "objects",
                sqlite_url="sqlite:///" + str(restored / "caseproof.db"),
                duckdb_path=str(restored / "bank.duckdb"),
                trail_feed_path=restored / "kit_v3/trail_feed.json",
                mock_services_url="http://127.0.0.1:1",
                local_ocr_url="http://127.0.0.1:1",
            )
        )
        prior = o.store.get(witness)
        # Promote only the controlled witness in the isolated copy. Other restored
        # cases are not processed or sent; original priorities remain untouched.
        with o.store.engine.begin() as db:
            pending = db.execute(
                text(
                    "SELECT count(*) FROM jobs WHERE case_id=:c AND revision=:r AND status='queued'"
                ),
                {"c": witness, "r": prior.revision},
            ).scalar()
            assert pending == 1
            db.execute(text("UPDATE jobs SET priority=0 WHERE status='queued'"))
        jid = o.jobs.enqueue(witness, prior.revision, priority=10)
        assert run_one(o.jobs, o) == jid
        assert o.jobs.get(jid)["status"] == "done"
        latest = o.store.get(witness)
        assert latest.revision == prior.revision + 1 and latest.valid_digest()
        assert o.store.get(witness, prior.revision).digest == prior.digest
        report["resume"] = {
            "witness": witness,
            "from_revision": prior.revision,
            "to_revision": latest.revision,
            "outbound_sent": False,
            "note": "Promoted witness only in isolated copy; durable worker resumed it",
        }
    assert inventory(backup) == before
    assert inventory(source) == before
    (output / "manifest.json").write_text(json.dumps(before, indent=2))
    report.update(files=len(before), passed=True, restore_isolated=True)
    (output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in {"sqlite", "duckdb"}}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--witness", required=True)
    args = parser.parse_args()
    run(args.source, args.output, args.witness)
