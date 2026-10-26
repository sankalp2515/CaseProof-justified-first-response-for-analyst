from filelock import FileLock


def test_lock_symlink_cannot_truncate_an_existing_file(tmp_path):
    target = tmp_path / "original.txt"
    target.write_text("preserve the original")
    lock_path = tmp_path / "untrusted.lock"
    lock_path.symlink_to(target)
    lock = FileLock(lock_path)
    try:
        lock.acquire(timeout=.05)
    except (OSError, TimeoutError):
        pass
    finally:
        if lock.is_locked:
            lock.release()
    assert target.read_text() == "preserve the original"
