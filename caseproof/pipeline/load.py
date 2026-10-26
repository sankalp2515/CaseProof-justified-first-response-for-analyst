import json
from pathlib import Path
from typing import Any


def load_input(root: Any, case_id: str) -> dict:
    """Project a fixture input onto operational fields without answer labels."""
    root = Path(root).resolve()
    if not case_id or any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in case_id
    ):
        raise ValueError("invalid case ID")
    path = root / "inputs" / (case_id + ".json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        k: v
        for k, v in data.items()
        if k
        in {
            "case_id",
            "customer_account",
            "reported_at",
            "first_contact",
            "initial_artifacts",
            "followup_artifacts",
        }
    }


def read_artifact(root: Any, item: Any) -> bytes:
    """Read an artifact only from the selected kit fixture directory."""
    root = Path(root).resolve()
    p = (root / item["path"]).resolve()
    if not p.is_relative_to(root / "fixtures"):
        raise ValueError("artifact outside fixtures")
    return p.read_bytes()


def load_case(o: Any, root: Any, case_id: str, new_id: Any = None) -> Any:
    """Create a case from public artifacts and operational simulator metadata."""
    world = Path(root) / "graph_world.json"
    if world.exists():
        from caseproof.graph.store import GraphStore

        GraphStore(o.s.duckdb_path).load_world(json.loads(world.read_text(encoding="utf-8")))
    data = load_input(root, case_id)
    cid = new_id or case_id
    if "customer_account" not in data:
        public = Path(root) / "mock_bank" / "ledger.json"
        if public.exists():
            row = next(
                (
                    r
                    for r in json.loads(public.read_text(encoding="utf-8"))
                    if r["case_id"] == case_id
                ),
                None,
            )
            if row:
                from datetime import timedelta

                from caseproof.domain.ledger import dt

                data["customer_account"] = row["customer_id"]
                data["reported_at"] = (dt(row["timestamp"]) + timedelta(hours=1)).isoformat()
                data["first_contact"] = (dt(row["timestamp"]) - timedelta(minutes=29)).isoformat()
    o.store.create(
        cid,
        customer_account=data.get("customer_account", case_id),
        reported_at=data.get("reported_at", "2026-10-01T12:30:00+05:30"),
        first_contact=data.get("first_contact", "2026-10-01T11:00:00+05:30"),
        kit_case_id=case_id,
    )
    transcripts = Path(root) / "renderer_transcripts.json"
    if (o.s.effective_mode == "mock" or o.s.allow_fallback) and transcripts.exists():
        o.fixtures.update(json.loads(transcripts.read_text(encoding="utf-8")))
    for item in data["initial_artifacts"]:
        o.intake.add(
            cid,
            read_artifact(root, item),
            item["mime_type"],
            item["kind"],
            artifact_id=item["artifact_id"],
        )
    return o.store.get(cid)
