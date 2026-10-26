"""Fast Docker worker liveness check; no application/database/model imports."""

import os
import socket
import time
from pathlib import Path


def replica_heartbeat(data_dir):
    """Per-replica heartbeat: scaled workers share /data, so each checks its own."""
    return Path(data_dir) / f"worker.{socket.gethostname()}.heartbeat"


def worker_healthy(data_dir, as_of=None, heartbeat=None):
    try:
        age = (time.time() if as_of is None else as_of) - (
            Path(heartbeat) if heartbeat else Path(data_dir) / "worker.heartbeat"
        ).stat().st_mtime
    except OSError:
        return False
    return 0 <= age < 20


if __name__ == "__main__":
    data = os.environ.get("DATA_DIR", "/data")
    raise SystemExit(0 if worker_healthy(data, heartbeat=replica_heartbeat(data)) else 1)
