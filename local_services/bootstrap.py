"""Idempotent creation of isolated Docker data; never reads host .env or answer labels."""

import json

from caseproof.config import Settings
from caseproof.domain.clock import clock_state
from caseproof.domain.ledger import dt
from caseproof.pipeline.load import load_case
from caseproof.pipeline.orchestrator import Orchestrator
from kitgen.v3 import generate


def main():
    settings = Settings()
    if settings.preloaded_demo:
        from local_services.demo_world import DemoWorld

        DemoWorld(Orchestrator(settings)).ensure()
    marker = settings.data_dir / "local_initialized_v2.json"
    if marker.exists():
        print("Local data already initialized; preserving evidence and approvals")
        return
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    generate(settings.eval_kit_v3, settings.duckdb_path)
    orchestrator = Orchestrator(settings)
    cid = "GOLD-001-LOCAL-V2"
    try:
        snap = orchestrator.store.get(cid)
    except KeyError:
        load_case(orchestrator, settings.eval_kit_v3, "GOLD-001", new_id=cid)
        snap = orchestrator.store.get(cid)
        snap.clock = clock_state(
            None, dt(orchestrator.store.metadata(cid)["reported_at"]), replay=True
        )
        old = snap.revision
        snap.revision += 1
        orchestrator.store.publish(snap, old, "local_replay_clock")
    orchestrator.jobs.enqueue(cid, snap.revision)
    marker.write_text(json.dumps({"version": 2, "case_id": cid, "provider": "local"}))
    print("Local bank, downstream feed, fixtures and GOLD case initialized")


if __name__ == "__main__":
    main()
