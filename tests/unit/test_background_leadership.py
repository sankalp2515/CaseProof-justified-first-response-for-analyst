import threading
from types import SimpleNamespace

from local_services.leadership import BackgroundLease, write_atomic
from local_services.worker import run_background_round


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_one_leader_at_a_time_and_handover_after_expiry(tmp_path):
    clock = Clock()
    first = BackgroundLease(tmp_path, ttl=30, owner="a", clock=clock)
    second = BackgroundLease(tmp_path, ttl=30, owner="b", clock=clock)
    assert first.acquire()
    assert not second.acquire()
    clock.now += 20
    assert first.acquire()  # Renewal extends the lease.
    clock.now += 20
    assert not second.acquire()
    clock.now += 31  # Leader stopped renewing (crashed): another replica takes over.
    assert second.acquire()
    assert not first.acquire()


def test_released_lease_is_taken_immediately(tmp_path):
    first = BackgroundLease(tmp_path, owner="a")
    second = BackgroundLease(tmp_path, owner="b")
    assert first.acquire()
    first.release()
    assert second.acquire()


def test_standby_replica_runs_no_background_tasks(tmp_path):
    clock = Clock()
    leader = BackgroundLease(tmp_path, owner="a", clock=clock)
    standby = BackgroundLease(tmp_path, owner="b", clock=clock)
    ran = []
    tasks = [("one", lambda: ran.append("one")), ("two", lambda: ran.append("two"))]
    settings = SimpleNamespace(data_dir=tmp_path)
    assert leader.acquire()
    run_background_round(standby, tasks, threading.Event(), settings)
    assert ran == []
    run_background_round(leader, tasks, threading.Event(), settings)
    assert ran == ["one", "two"]


def test_task_failure_is_recorded_without_stopping_the_round(tmp_path):
    def broken():
        raise ValueError("feed down")

    ran = []
    lease = BackgroundLease(tmp_path, owner="a")
    settings = SimpleNamespace(data_dir=tmp_path)
    tasks = [("feed", broken), ("clocks", lambda: ran.append("clocks"))]
    run_background_round(lease, tasks, threading.Event(), settings)
    assert ran == ["clocks"]
    assert "ValueError" in (tmp_path / "feed_error.json").read_text()


def test_concurrent_atomic_writes_never_collide(tmp_path):
    target = tmp_path / "cursor.json"
    errors = []

    def writer(n):
        try:
            for i in range(50):
                write_atomic(target, {"writer": n, "i": i})
        except Exception as error:  # A shared temp name would raise here.
            errors.append(error)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert not list(tmp_path.glob("*.tmp"))
