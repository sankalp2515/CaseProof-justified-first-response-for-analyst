import time
from types import SimpleNamespace

import pytest

from caseproof.adapters.local_storage import LocalStorage
from caseproof.adapters.quarantine_storage import EvidenceNotReady, QuarantineStorage
from local_services import cloud_scanner
from tests.unit.test_firestore_state import Documents


@pytest.mark.parametrize("status", ["clean", "infected", "unavailable"])
def test_quarantined_upload_cannot_be_read_before_a_digest_bound_clean_scan(tmp_path, status):
    from hashlib import sha256

    data = b"synthetic evidence"
    digest = sha256(data).hexdigest()

    def scan(*args, **kwargs):
        if status == "unavailable":
            raise RuntimeError("scanner unavailable")
        return {
            "status": status,
            "sha256": digest,
            "engine": "clamav",
            "signatures_at": time.time(),
        }

    docs = Documents()
    storage = QuarantineStorage(
        LocalStorage(tmp_path / "quarantine"),
        LocalStorage(tmp_path / "clean"),
        docs,
        SimpleNamespace(post=scan),
    )
    key, _ = storage.put(data, "text/plain")
    with pytest.raises(EvidenceNotReady):
        storage.read(key)
    if status == "unavailable":
        with pytest.raises(RuntimeError):
            storage.scan(digest)
        assert docs.get("evidence_scans/" + digest)["status"] == "pending"
    else:
        storage.scan(digest)
    if status == "clean":
        assert storage.read(key) == data
    else:
        with pytest.raises(EvidenceNotReady):
            storage.read(key)


@pytest.mark.parametrize(
    "reply, expected",
    [
        ("stream: OK", "clean"),
        ("stream: Eicar-Signature FOUND", "infected"),
        ("INSTREAM size limit exceeded. ERROR", None),
        ("", None),
    ],
)
def test_scanner_errors_are_never_clean(monkeypatch, reply, expected):
    monkeypatch.setattr(cloud_scanner, "signatures", lambda: time.time())
    monkeypatch.setattr(cloud_scanner, "verify_engine", lambda: "1.4.6")
    monkeypatch.setattr(cloud_scanner, "daemon_command", lambda *a, **kw: reply)
    if expected:
        assert cloud_scanner.scan_bytes(b"safe test text", "text/plain")["status"] == expected
    else:
        with pytest.raises(RuntimeError, match="UNAVAILABLE"):
            cloud_scanner.scan_bytes(b"test text", "text/plain")


def test_unreachable_resident_engine_is_unavailable_not_clean(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAMD_SOCKET", str(tmp_path / "missing.sock"))
    monkeypatch.setattr(cloud_scanner, "signatures", lambda: time.time())
    monkeypatch.setattr(cloud_scanner, "verify_engine", lambda: "1.4.6")
    with pytest.raises(RuntimeError, match="DAEMON_UNAVAILABLE"):
        cloud_scanner.scan_bytes(b"safe test text", "text/plain")


@pytest.mark.parametrize("has_old_database", [False, True])
def test_signature_set_is_required_and_expiry_fails_closed(tmp_path, monkeypatch, has_old_database):
    import os

    monkeypatch.setenv("CLAMAV_DATABASE", str(tmp_path))
    if has_old_database:
        database = tmp_path / "daily.cvd"
        database.write_bytes(b"test-only placeholder")
        stale = time.time() - 73 * 3600
        os.utime(database, (stale, stale))
    with pytest.raises(RuntimeError, match="SIGNATURES"):
        cloud_scanner.signatures()


def cvd_header(published):
    header = f"ClamAV-VDB:16 Oct 2026 00-00 +0000:1:1:90:md5:sig:builder:{int(published)}"
    return header.encode().ljust(512, b" ")


def test_recent_bytecode_or_copy_time_cannot_hide_expired_daily_signatures(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAMAV_DATABASE", str(tmp_path))
    (tmp_path / "main.cvd").write_bytes(cvd_header(time.time() - 365 * 86400))
    (tmp_path / "daily.cvd").write_bytes(cvd_header(time.time() - 73 * 3600))
    (tmp_path / "bytecode.cvd").write_bytes(cvd_header(time.time()))
    with pytest.raises(RuntimeError, match="SIGNATURES_STALE"):
        cloud_scanner.signatures()


def test_signature_attestation_uses_daily_publication_time(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAMAV_DATABASE", str(tmp_path))
    published = int(time.time()) - 3600
    (tmp_path / "main.cvd").write_bytes(cvd_header(published - 365 * 86400))
    (tmp_path / "daily.cvd").write_bytes(cvd_header(published))
    assert cloud_scanner.signatures() == published


@pytest.mark.parametrize("version", ["1.4.3", "1.4.5", "1.5.3"])
def test_scanner_rejects_an_unapproved_engine_version(monkeypatch, version):
    monkeypatch.setattr(
        cloud_scanner.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=f"ClamAV {version}/28155/today\n"),
    )
    with pytest.raises(RuntimeError, match="ENGINE_VERSION"):
        cloud_scanner.verify_engine()


def test_missing_engine_is_an_explicit_unavailable_state(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("clamscan missing")

    monkeypatch.setattr(cloud_scanner.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="ENGINE_UNAVAILABLE"):
        cloud_scanner.verify_engine()


def test_scanner_uses_the_same_database_directory_as_its_freshness_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAMAV_DATABASE", str(tmp_path))
    config = cloud_scanner.clamd_config().splitlines()
    assert "DatabaseDirectory " + str(tmp_path) in config
    # Reloads must not hold two signature sets in the 2 GiB scanner instance.
    assert "ConcurrentDatabaseReload no" in config
    for parser in ("Archive", "PE", "ELF", "OLE2", "PDF", "HTML", "Mail"):
        assert f"Scan{parser} no" in config


def test_stale_signatures_refresh_reload_the_engine_then_require_a_new_scan(monkeypatch):
    calls = []
    commands = []
    state = {"fresh": False}

    def signatures():
        if not state["fresh"]:
            raise RuntimeError("SCANNER_SIGNATURES_STALE")
        return 123

    def update(*args, **kwargs):
        calls.append(args[0])
        state["fresh"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cloud_scanner, "signatures", signatures)
    monkeypatch.setattr(cloud_scanner.subprocess, "run", update)
    monkeypatch.setattr(
        cloud_scanner,
        "daemon_command",
        lambda command, **kw: commands.append(command) or "RELOADING",
    )
    monkeypatch.setattr(cloud_scanner, "_last_refresh", None, raising=False)
    with pytest.raises(RuntimeError, match="REFRESHED_RETRY"):
        cloud_scanner.current_signatures()
    assert cloud_scanner.current_signatures() == 123
    assert len(calls) == 1 and calls[0][0] == "freshclam"
    assert commands == [b"RELOAD"]


def test_refresh_without_engine_reload_is_unavailable(monkeypatch):
    state = {"fresh": False}

    def signatures():
        if not state["fresh"]:
            raise RuntimeError("SCANNER_SIGNATURES_STALE")
        return 123

    def update(*args, **kwargs):
        state["fresh"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cloud_scanner, "signatures", signatures)
    monkeypatch.setattr(cloud_scanner.subprocess, "run", update)
    monkeypatch.setattr(cloud_scanner, "daemon_command", lambda *a, **kw: "")
    monkeypatch.setattr(cloud_scanner, "_last_refresh", None, raising=False)
    with pytest.raises(RuntimeError, match="RELOAD_UNAVAILABLE"):
        cloud_scanner.current_signatures()


def test_failed_signature_refresh_is_throttled_and_never_clean(monkeypatch):
    calls = []

    def stale():
        raise RuntimeError("SCANNER_SIGNATURES_STALE")

    monkeypatch.setattr(cloud_scanner, "signatures", stale)
    monkeypatch.setattr(cloud_scanner, "_last_refresh", None, raising=False)
    monkeypatch.setattr(
        cloud_scanner.subprocess,
        "run",
        lambda *a, **kw: calls.append(a) or SimpleNamespace(returncode=1),
    )
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cloud_scanner.current_signatures()
    assert len(calls) == 1
