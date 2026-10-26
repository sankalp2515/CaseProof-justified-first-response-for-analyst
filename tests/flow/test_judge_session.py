from fastapi.testclient import TestClient

from caseproof.api.app import create_app
from tests.flow.test_victim_flow import settings


def test_practice_sessions_have_independent_catalogues_and_queues(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as a, TestClient(app) as b:
        original = b.get("/v1/victim/demo-customers").json()
        app.state.orchestrator.store.create("LEGACY", customer_account="old")
        made = a.post("/v1/victim/demo-session")
        assert made.status_code == 200 and made.json()["complaints_created"] == 0
        mine = a.get("/v1/victim/demo-customers").json()
        assert mine["customers"][0]["account"] != original["customers"][0]["account"]
        assert b.get("/v1/victim/demo-customers").json() == original
        assert a.get("/v1/workspace?scope=active").json()["cases"] == []
        assert len(a.get("/v1/workspace?scope=all").json()["cases"]) == 1
        assert (
            a.post(
                "/v1/victim/sessions", json={"customer_id": original["customers"][0]["account"]}
            ).status_code
            == 422
        )
        assert (
            a.post("/v1/victim/demo-session", headers={"Origin": "http://evil.invalid"}).status_code
            == 403
        )


def test_prebuilt_practice_worlds_are_claimed_once_each(tmp_path):
    from local_services.demo_world import DemoWorld

    app = create_app(settings(tmp_path))
    o = app.state.orchestrator
    o.s.practice_pool_size = 2
    ids = iter(["judge-00000000000a", "judge-00000000000b", "judge-00000000000c"])
    DemoWorld.fill_pool(o, lambda: next(ids))
    ready = o.s.data_dir / "demo_worlds" / "ready"
    assert sorted(p.name for p in ready.iterdir()) == ["judge-00000000000a", "judge-00000000000b"]
    with TestClient(app) as a, TestClient(app) as b, TestClient(app) as c:
        claimed = [x.post("/v1/victim/demo-session").json()["session_id"] for x in (a, b, c)]
    # Two pooled worlds, then an on-demand world; no session shares a world.
    assert claimed[:2] == ["judge-00000000000a", "judge-00000000000b"]
    assert claimed[2] not in claimed[:2] and claimed[2].startswith("judge-")
    assert not list(ready.iterdir())
    for sid in claimed:
        assert DemoWorld(o, sid).path.exists()


def test_concurrent_pool_fillers_never_exceed_the_pool_size(tmp_path):
    import itertools
    import threading

    from local_services.demo_world import DemoWorld

    app = create_app(settings(tmp_path))
    o = app.state.orchestrator
    o.s.practice_pool_size = 2
    counter = itertools.count()
    lock = threading.Lock()

    def new_id():
        with lock:
            return f"judge-{next(counter):012x}"

    threads = [threading.Thread(target=DemoWorld.fill_pool, args=(o, new_id)) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    DemoWorld.fill_pool(o, new_id)  # A later round tops up to, not past, the size.
    assert len(list((o.s.data_dir / "demo_worlds" / "ready").glob("judge-*"))) == 2


def test_chosen_scam_timing_shapes_a_fresh_world_and_marks_the_victim(tmp_path):
    from datetime import datetime, timezone

    app = create_app(settings(tmp_path))
    with TestClient(app) as visitor:
        made = visitor.post("/v1/victim/demo-session", json={"minutes_ago": 10})
        assert made.status_code == 200
        customers = visitor.get("/v1/victim/demo-customers").json()["customers"]
        victims = [c for c in customers if c.get("incident")]
        assert victims and all(c["incident"]["minutes_ago"] == 10 for c in victims)
        assert len({c["display_name"] for c in customers}) == len(customers)
        victim = victims[0]
        visitor.post("/v1/victim/sessions", json={"customer_id": victim["account"]})
        me = visitor.get("/v1/victim/me").json()
        scam = next(t for t in me["transactions"] if t["txn_id"] == victim["incident"]["txn_id"])
        age = datetime.now(timezone.utc) - datetime.fromisoformat(scam["ts"])
        assert 9 * 60 <= age.total_seconds() <= 12 * 60
        assert visitor.post("/v1/victim/demo-session", json={"minutes_ago": 2}).status_code == 422
