import duckdb
import pytest
from pydantic import ValidationError

from caseproof.graph.store import GraphStore


def test_invalid_later_seed_row_cannot_leave_a_partial_world(tmp_path):
    store = GraphStore(str(tmp_path / "bank.duckdb"))
    world = {
        "accounts": [
            {"id": "A", "bank": "Cedar", "label": "A", "kind": "customer"},
            {"id": "BROKEN", "bank": "Cedar", "label": "B", "kind": "unknown"},
        ]
    }
    with pytest.raises(ValidationError):
        store.load_world(world)
    with store.bank.connect() as db:
        assert db.execute("SELECT count(*) FROM trail_accounts").fetchone()[0] == 0


def test_seed_replay_is_idempotent_and_never_preloads_downstream_edges(tmp_path):
    store = GraphStore(str(tmp_path / "bank.duckdb"))
    world = {
        "accounts": [
            {"id": "A", "bank": "Cedar", "label": "A", "kind": "customer"},
        ],
        "transfers": [{"source": "cfcfrms_update:NOT-RECEIVED"}],
    }
    store.load_world(world)
    store.load_world(world)
    with store.bank.connect() as db:
        assert db.execute("SELECT count(*) FROM trail_accounts").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM trail_transfers").fetchone()[0] == 0


def test_storage_error_after_valid_accounts_rolls_back_the_entire_seed(tmp_path):
    store = GraphStore(str(tmp_path / "bank.duckdb"))
    world = {
        "accounts": [
            {"id": "A", "bank": "Cedar", "label": "A", "kind": "customer"},
        ],
        "transfers": [
            {
                "txn_id": "OVERFLOW",
                "ts": "2026-10-16T12:00:00Z",
                "from_account": "A",
                "to_account": "B",
                "amount_minor": 2**70,
                "channel": "UPI",
                "reference": "R",
                "source": "ledger",
            }
        ],
    }
    with pytest.raises(duckdb.Error):
        store.load_world(world)
    with store.bank.connect() as db:
        assert db.execute("SELECT count(*) FROM trail_accounts").fetchone()[0] == 0
