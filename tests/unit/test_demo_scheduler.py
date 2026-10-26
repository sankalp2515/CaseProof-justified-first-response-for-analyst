import json
from types import SimpleNamespace

from sqlalchemy import create_engine, text

from local_services.demo_world import DemoWorld


def test_new_complaint_refreshes_past_filing_time_without_waiting_for_ttl(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE cases(tenant_id TEXT,metadata TEXT)"))
        for account, stamp in [("NEW", 1990), ("OLD", 900), ("THIRD", 800)]:
            from datetime import datetime, timezone

            db.execute(
                text("INSERT INTO cases VALUES('demo',:m)"),
                {
                    "m": json.dumps(
                        {
                            "customer_account": account,
                            "reported_at": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                        }
                    )
                },
            )
    world = DemoWorld(
        SimpleNamespace(s=SimpleNamespace(data_dir=tmp_path), store=SimpleNamespace(engine=engine))
    )
    monkeypatch.setattr(
        world,
        "worlds",
        lambda: [
            {
                "customers": [
                    {"account": a, "network_id": a} for a in ("NEW", "OLD", "THIRD", "UNUSED")
                ]
            }
        ],
    )
    cursor = tmp_path / "world_observations.json"
    cursor.write_text(
        json.dumps(
            {
                "networks": {
                    "NEW": {"status": "observed", "attempt_at": 1980, "observed_at": 1980},
                    "OLD": {"status": "observed", "attempt_at": 1000, "observed_at": 1000},
                    "THIRD": {"status": "observed", "attempt_at": 900, "observed_at": 900},
                }
            }
        )
    )
    monkeypatch.setattr("local_services.demo_world.time.time", lambda: 2000)
    calls = []

    class Network:
        def __init__(self, o):
            pass

        def publish_reports(self, nid, actor, refresh):
            calls.append(nid)

    monkeypatch.setattr("local_services.demo_world.BankNetwork", Network)
    world.tick()
    assert calls == ["NEW", "THIRD"]  # urgent coverage first; bounded background work
    world.tick()
    assert calls == ["NEW", "THIRD", "OLD"]
    # Routine idle polling must not republish fresh observations after two minutes.
    monkeypatch.setattr("local_services.demo_world.time.time", lambda: 2121)
    world.tick()
    assert calls == ["NEW", "THIRD", "OLD"]
    assert "UNUSED" not in json.loads(cursor.read_text())["networks"]


def test_failed_bank_refresh_backs_off_without_claiming_an_observation(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE cases(tenant_id TEXT,metadata TEXT)"))
        db.execute(
            text("INSERT INTO cases VALUES('demo',:m)"),
            {
                "m": json.dumps(
                    {"customer_account": "A", "reported_at": "1970-01-01T00:30:00+00:00"}
                )
            },
        )
    world = DemoWorld(
        SimpleNamespace(s=SimpleNamespace(data_dir=tmp_path), store=SimpleNamespace(engine=engine))
    )
    monkeypatch.setattr(
        world, "worlds", lambda: [{"customers": [{"account": "A", "network_id": "N"}]}]
    )
    monkeypatch.setattr("local_services.demo_world.time.time", lambda: 2000)
    calls = []

    class Network:
        def __init__(self, o):
            pass

        def publish_reports(self, nid, actor, refresh):
            calls.append(nid)
            raise TimeoutError()

    monkeypatch.setattr("local_services.demo_world.BankNetwork", Network)
    world.tick()
    world.tick()
    assert calls == ["N"]
    state = json.loads((tmp_path / "world_observations.json").read_text())["networks"]["N"]
    assert state["status"] == "unavailable" and "observed_at" not in state


def test_slow_background_poll_does_not_block_durable_job_consumer(monkeypatch):
    import threading

    from local_services import worker

    entered, finished, stopped = threading.Event(), threading.Event(), threading.Event()
    calls = []

    def slow_poll(o, stop):
        entered.set()
        stop.wait(5)
        finished.set()

    def consume(jobs, o):
        assert entered.wait(1)
        assert not finished.is_set()
        calls.append(jobs)
        stopped.set()

    monkeypatch.setattr(worker, "poll_background", slow_poll)
    monkeypatch.setattr(worker, "run_one", consume)
    worker.run_worker(SimpleNamespace(jobs="durable-intents"), stopped)
    assert calls == ["durable-intents"] and finished.is_set()
