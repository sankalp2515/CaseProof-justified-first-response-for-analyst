"""Private bounded ClamAV scanner. Unavailable or stale signatures never mean clean."""

import hashlib
import os
import re
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from caseproof.adapters.object_validation import validate_evidence

app = FastAPI(title="CaseProof evidence scanner")
_refresh_lock = threading.Lock()
_last_refresh = None
NUL = bytes(1)


def verify_engine():
    try:
        result = subprocess.run(
            ["clamscan", "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("SCANNER_ENGINE_UNAVAILABLE") from None
    version = re.match(r"ClamAV (\d+\.\d+\.\d+)(?:/|\s|$)", result.stdout or "")
    if result.returncode or not version or version[1] != "1.4.6":
        raise RuntimeError("SCANNER_ENGINE_VERSION_UNAPPROVED")
    return version[1]


def database_directory():
    return os.environ.get("CLAMAV_DATABASE", "/var/lib/clamav")


def daemon_socket():
    return os.environ.get("CLAMD_SOCKET", "/tmp/clamd.sock")


def clamd_config(database=None, socket_path=None):
    """Resident engine: signatures load once at startup, not once per evidence file."""
    return "\n".join(
        [
            "DatabaseDirectory " + (database or database_directory()),
            "LocalSocket " + (socket_path or daemon_socket()),
            "LocalSocketMode 600",
            "Foreground yes",
            # One resident engine within 2 GiB: block scans during reload, never clean.
            "ConcurrentDatabaseReload no",
            "SelfCheck 0",
            "MaxThreads 4",
            "MaxQueue 8",
            "ReadTimeout 30",
            "CommandReadTimeout 10",
            "StreamMaxLength 6M",
            "MaxFileSize 6M",
            "MaxScanSize 6M",
            "ScanArchive no",
            # Evidence is validated PNG/JPEG/text before scanning. Executable, document,
            # mail and container parsers carry the unfixed upstream parser findings
            # and are not needed, so their attack surface is disabled.
            "ScanPE no",
            "ScanELF no",
            "ScanOLE2 no",
            "ScanPDF no",
            "ScanSWF no",
            "ScanHTML no",
            "ScanXMLDOCS no",
            "ScanHWP3 no",
            "ScanOneNote no",
            "ScanMail no",
            "",
        ]
    )


def daemon_command(command, payload=None, timeout=30):
    """Exchange one null-terminated clamd command over the private Unix socket."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(daemon_socket())
            connection.sendall(b"z" + command + NUL)
            if payload is not None:
                for start in range(0, len(payload), 65536):
                    chunk = payload[start : start + 65536]
                    connection.sendall(struct.pack(">I", len(chunk)) + chunk)
                connection.sendall(struct.pack(">I", 0))
            reply = bytearray()
            while not reply.endswith(NUL):
                chunk = connection.recv(4096)
                if not chunk:
                    break
                reply.extend(chunk)
    except (OSError, AttributeError):  # AttributeError: no Unix sockets on this host
        raise RuntimeError("SCANNER_DAEMON_UNAVAILABLE") from None
    return reply.rstrip(NUL).decode("utf-8", "replace").strip()


def daemon_ready():
    return daemon_command(b"PING", timeout=5) == "PONG"


def daemon_scan(data):
    reply = daemon_command(b"INSTREAM", data)
    if reply == "stream: OK":
        return "clean"
    if reply.startswith("stream: ") and reply.endswith(" FOUND"):
        return "infected"
    raise RuntimeError("SCANNER_UNAVAILABLE")


def signatures():
    directory = Path(database_directory())
    daily = None
    for name in ("main", "daily"):
        candidates = [
            p for suffix in (".cvd", ".cld") if (p := directory / (name + suffix)).is_file()
        ]
        if len(candidates) != 1:
            raise RuntimeError("SCANNER_SIGNATURES_UNAVAILABLE")
        with candidates[0].open("rb") as source:
            header = source.read(512).rstrip(b" \x00\r\n")
        try:
            if not header.startswith(b"ClamAV-VDB:"):
                raise ValueError("invalid header")
            published = int(header.split(b":")[-1])
        except (ValueError, IndexError):
            raise RuntimeError("SCANNER_SIGNATURES_INVALID") from None
        if name == "daily":
            daily = published
    if daily is None or not time.time() - 72 * 3600 <= daily <= time.time() + 300:
        raise RuntimeError("SCANNER_SIGNATURES_STALE")
    return daily


def current_signatures():
    """Recover long-lived instances without relying on idle background CPU."""
    global _last_refresh
    try:
        return signatures()
    except RuntimeError:
        pass
    if not _refresh_lock.acquire(blocking=False):
        raise RuntimeError("SCANNER_REFRESH_IN_PROGRESS")
    try:
        if _last_refresh is not None and time.monotonic() - _last_refresh < 300:
            raise RuntimeError("SCANNER_REFRESH_COOLDOWN")
        _last_refresh = time.monotonic()
        try:
            result = subprocess.run(
                ["freshclam", "--config-file=/app/freshclam.conf", "--stdout"],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("SCANNER_REFRESH_UNAVAILABLE") from None
        if result.returncode:
            raise RuntimeError("SCANNER_REFRESH_UNAVAILABLE")
        signatures()
        # The resident engine keeps old signatures until told to reload them.
        if daemon_command(b"RELOAD", timeout=10) != "RELOADING":
            raise RuntimeError("SCANNER_RELOAD_UNAVAILABLE")
    finally:
        _refresh_lock.release()
    # A refreshed request is retried after the engine reload rather than adding
    # a scan to a 60s refresh and exceeding the authenticated service deadline.
    raise RuntimeError("SCANNER_SIGNATURES_REFRESHED_RETRY")


def scan_bytes(data, mime):
    validate_evidence(data, mime)
    version = verify_engine()
    updated = current_signatures()
    status = daemon_scan(data)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "status": status,
        "engine": "clamav",
        "engine_version": version,
        "signatures_at": updated,
    }


@app.get("/health")
def health():
    try:
        if not daemon_ready():
            raise RuntimeError("SCANNER_DAEMON_UNAVAILABLE")
        return {"ok": True, "engine_version": verify_engine(), "signatures_at": signatures()}
    except RuntimeError:
        raise HTTPException(503, "SCANNER_UNAVAILABLE") from None


@app.post("/scan")
async def scan(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, "file_limit")
    import asyncio

    try:
        return await asyncio.to_thread(
            scan_bytes, bytes(data), request.headers.get("content-type", "")
        )
    except ValueError:
        raise HTTPException(422, "invalid_evidence") from None
    except (RuntimeError, subprocess.TimeoutExpired):
        raise HTTPException(503, "SCANNER_UNAVAILABLE") from None
