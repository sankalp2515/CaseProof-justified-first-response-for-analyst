"""Refresh signatures, load one resident engine, then accept traffic; never deploys."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Keep updater output out of evidence/request logs; startup failure stays explicit.
try:
    result = subprocess.run(
        ["freshclam", "--config-file=/app/freshclam.conf", "--stdout"], timeout=60
    )
except subprocess.TimeoutExpired:
    result = None
from local_services.cloud_scanner import clamd_config, daemon_ready, signatures, verify_engine

try:
    verify_engine()
    signatures()  # A failed refresh is acceptable only while the trusted existing set is fresh.
except RuntimeError:
    raise SystemExit("Scanner startup failed: fresh signatures unavailable") from None

config = Path(os.environ.get("CLAMD_CONFIG", "/tmp/clamd.conf"))
config.write_text(clamd_config())
daemon = subprocess.Popen(["clamd", "--config-file=" + str(config)])
deadline = time.monotonic() + float(os.environ.get("CLAMD_START_SECONDS", "150"))
while True:
    if daemon.poll() is not None:
        raise SystemExit("Scanner startup failed: engine exited while loading signatures")
    try:
        if daemon_ready():
            break
    except RuntimeError:
        pass
    if time.monotonic() >= deadline:
        daemon.kill()
        raise SystemExit("Scanner startup failed: engine did not load signatures in time")
    time.sleep(0.5)
print("Scanner engine resident; signatures loaded once", flush=True)

server = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "local_services.cloud_scanner:app",
        "--host",
        "0.0.0.0",
        "--port",
        os.environ.get("PORT", "8080"),
        "--no-access-log",
    ]
)


def stop(*_):
    for process in (server, daemon):
        if process.poll() is None:
            process.terminate()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
# Either process exiting ends the instance: a server without its engine is unavailable.
while server.poll() is None and daemon.poll() is None:
    time.sleep(0.5)
stop()
for process in (server, daemon):
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
raise SystemExit(server.returncode or daemon.returncode or 0)
