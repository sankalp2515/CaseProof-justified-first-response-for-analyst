import json
import time
from types import SimpleNamespace

from local_services.demo_world import DemoWorld


def test_old_or_previous_catalogues_are_not_assigned_but_history_is_preserved(tmp_path):
    o = SimpleNamespace(s=SimpleNamespace(data_dir=tmp_path))
    worlds = tmp_path / "demo_worlds"
    ready = worlds / "ready"
    ready.mkdir(parents=True)
    for sid, version, age in [
        ("judge-000000000001", 5, 901),
        ("judge-000000000002", 1, 0),
        ("judge-000000000003", 5, 0),
    ]:
        (worlds / (sid + ".json")).write_text(
            json.dumps(
                {
                    "version": version,
                    "created_at": time.time() - age,
                }
            )
        )
        (ready / sid).touch()
    assert DemoWorld.claim_ready(o) == "judge-000000000003"
    assert len(list(worlds.glob("*.json"))) == 3
    assert DemoWorld.claim_ready(o) is None


def test_v3_catalogue_keeps_legacy_default_customers_resolvable(tmp_path):
    o = SimpleNamespace(s=SimpleNamespace(data_dir=tmp_path))
    (tmp_path / "preloaded_world_v1.json").write_text(
        json.dumps(
            {
                "customers": [{"account": "LEGACY", "display_name": "Earlier customer"}],
            }
        )
    )
    world = DemoWorld(o)
    world.ensure = lambda: {"customers": [{"account": "CURRENT"}]}
    assert world.customer("LEGACY")["display_name"] == "Earlier customer"
    assert world.customer("CURRENT")["account"] == "CURRENT"
