import os

from local_services.health import worker_healthy


def test_heartbeat_health_is_lightweight_and_rejects_missing_old_or_future_file(tmp_path):
    heartbeat = tmp_path / "worker.heartbeat"
    assert not worker_healthy(tmp_path, 100)
    heartbeat.touch()
    os.utime(heartbeat, (90, 90))
    assert worker_healthy(tmp_path, 100)
    assert not worker_healthy(tmp_path, 110)
    assert not worker_healthy(tmp_path, 80)


def test_each_replica_checks_its_own_heartbeat(tmp_path):
    from local_services.health import replica_heartbeat

    (tmp_path / "worker.heartbeat").touch()  # Another replica is alive.
    assert not worker_healthy(tmp_path, heartbeat=replica_heartbeat(tmp_path))
    replica_heartbeat(tmp_path).touch()
    assert worker_healthy(tmp_path, heartbeat=replica_heartbeat(tmp_path))
