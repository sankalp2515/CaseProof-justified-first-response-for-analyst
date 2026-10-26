"""Single leader for worker background polling across replicas on a shared volume.

Job processing is already replica-safe through per-job leases. Background polling
(feed, observations, clocks, practice pool, outbound recovery) must run in one
replica at a time: the leader renews an expiring lease; if it dies, another
replica takes over once the lease expires.
"""

import json
import os
import socket
import time
import uuid
from pathlib import Path

from filelock import FileLock


class BackgroundLease:
    def __init__(self, data_dir, ttl=45.0, owner=None, clock=time.time):
        self.path = Path(data_dir) / "background.lease"
        self.ttl = ttl
        self.owner = owner or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.clock = clock

    def acquire(self):
        """Take or renew the lease; False while another live replica holds it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock", timeout=10):
            try:
                current = json.loads(self.path.read_text())
            except (OSError, ValueError):
                current = {}
            now = self.clock()
            if current.get("owner") not in (None, self.owner) and current.get("expires", 0) > now:
                return False
            write_atomic(self.path, {"owner": self.owner, "expires": now + self.ttl})
            return True

    def release(self):
        with FileLock(str(self.path) + ".lock", timeout=10):
            try:
                if json.loads(self.path.read_text()).get("owner") == self.owner:
                    self.path.unlink()
            except (OSError, ValueError):
                pass


def write_atomic(path, data):
    """Replace a JSON file via a unique temporary name, safe across replicas."""
    path = Path(path)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(data))
    try:
        for attempt in range(8):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                # Windows can briefly deny replacement while another writer's
                # rename handle is closing. Retain atomicity and bound retries.
                if os.name != "nt" or attempt == 7:
                    raise
                time.sleep(min(0.005 * 2**attempt, 0.1))
    finally:
        temporary.unlink(missing_ok=True)
