"""Network-free acceptance of the actual scanner image and trusted engine."""

import base64
import json
import os
import subprocess
import tempfile
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

from local_services.cloud_scanner import (
    clamd_config,
    daemon_ready,
    scan_bytes,
    signatures,
    verify_engine,
)


def start_engine():
    """Load the same resident engine the service uses and time the one-off load."""
    config = Path(tempfile.gettempdir()) / "caseproof-check-clamd.conf"
    config.write_text(clamd_config())
    started = time.perf_counter()
    daemon = subprocess.Popen(["clamd", "--config-file=" + str(config)])
    while time.perf_counter() - started < 150:
        if daemon.poll() is not None:
            raise AssertionError("resident engine exited while loading signatures")
        try:
            if daemon_ready():
                return daemon, round(time.perf_counter() - started, 3)
        except RuntimeError:
            pass
        time.sleep(0.5)
    daemon.kill()
    raise AssertionError("resident engine did not load signatures within 150s")


def main():
    version = verify_engine()
    daemon, load_seconds = start_engine()
    print(json.dumps({"check": "engine_load", "elapsed_seconds": load_seconds}), flush=True)
    try:
        run_checks(version, load_seconds)
    finally:
        daemon.terminate()
        daemon.wait(timeout=20)


def run_checks(version, load_seconds):
    png = BytesIO()
    Image.new("RGB", (64, 32), "white").save(png, format="PNG")
    eicar = base64.b64decode(
        "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElWSVJVUy1URVNULUZJTEUhJEgrSCo="
    )
    results = {}
    for name, data, mime, expected in (
        ("clean_text", b"Synthetic bank complaint evidence", "text/plain", "clean"),
        ("clean_png", png.getvalue(), "image/png", "clean"),
        ("standard_eicar", eicar, "text/plain", "infected"),
    ):
        started = time.perf_counter()
        result = scan_bytes(data, mime)
        assert result["status"] == expected, (name, result)
        results[name] = {**result, "elapsed_seconds": round(time.perf_counter() - started, 3)}
        print(json.dumps({"check": name, **results[name]}), flush=True)
    previous = os.environ.get("CLAMAV_DATABASE")
    try:
        with tempfile.TemporaryDirectory(prefix="caseproof-signature-check-") as folder:
            os.environ["CLAMAV_DATABASE"] = folder
            try:
                signatures()
            except RuntimeError:
                results["missing_signatures"] = "rejected"
            else:
                raise AssertionError("missing signature set accepted")
            for name, published in (
                ("main", time.time() - 365 * 86400),
                ("daily", time.time() - 73 * 3600),
            ):
                header = f"ClamAV-VDB:test:1:1:90:md5:sig:builder:{int(published)}"
                (Path(folder) / (name + ".cvd")).write_bytes(header.encode().ljust(512, b" "))
            try:
                signatures()
            except RuntimeError:
                results["stale_signatures"] = "rejected"
            else:
                raise AssertionError("expired signature set accepted")
    finally:
        if previous is None:
            os.environ.pop("CLAMAV_DATABASE", None)
        else:
            os.environ["CLAMAV_DATABASE"] = previous
    results["engine_load_seconds"] = load_seconds
    print(json.dumps({"ok": True, "engine_version": version, "checks": results}), flush=True)


if __name__ == "__main__":
    main()
