from hashlib import sha256

import pytest

from caseproof.adapters.gcs_storage import GCSStorage
from caseproof.adapters.storage import build_storage
from caseproof.config import Settings


class Response:
    def __init__(self, status, content=b""):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ObjectService:
    """Minimal create-only object server; deliberately permits corrupt stored bytes."""

    def __init__(self):
        self.objects = {}
        self.calls = []

    def post(self, url, *, params, data, headers, timeout):
        self.calls.append(("POST", url, params, headers))
        assert params["ifGenerationMatch"] == 0
        name = params["name"]
        if name in self.objects:
            return Response(412)
        self.objects[name] = data
        return Response(200)

    def get(self, url, *, params, timeout):
        from urllib.parse import unquote

        self.calls.append(("GET", url, params))
        assert params == {"alt": "media"}
        name = unquote(url.split("/o/")[1])
        return Response(200, self.objects[name]) if name in self.objects else Response(404)


def test_content_addressed_create_only_duplicate_and_verified_read():
    service = ObjectService()
    storage = GCSStorage("private-caseproof", session=service)
    data = b"Synthetic complaint only"
    key, digest = storage.put(data, "text/plain")
    assert digest == sha256(data).hexdigest() and key == digest[:2] + "/" + digest
    assert storage.read(key) == data
    assert storage.put(data, "text/plain") == (key, digest)
    assert (
        service.calls[0][1]
        == "https://storage.googleapis.com/upload/storage/v1/b/private-caseproof/o"
    )
    assert service.calls[0][3]["Content-Type"] == "text/plain"
    service.objects[key] = b"tampered"
    with pytest.raises(ValueError, match="corrupt_object"):
        storage.read(key)
    with pytest.raises(ValueError, match="corrupt_object"):
        storage.put(data, "text/plain")


@pytest.mark.parametrize("key", ["../private", "aa/" + "b" * 64, "a" * 64, "aa/" + "a" * 63 + "Z"])
def test_invalid_keys_never_reach_network(key):
    service = ObjectService()
    with pytest.raises(ValueError, match="invalid_object_key"):
        GCSStorage("private-caseproof", session=service).read(key)
    assert service.calls == []


@pytest.mark.parametrize(
    "data,mime,error",
    [
        (b"", "text/plain", "file_limit"),
        (b"x" * (5 * 1024 * 1024 + 1), "text/plain", "file_limit"),
        (b"\x00secret", "text/plain", "invalid_text"),
        (b"\xff", "text/plain", "invalid_text"),
        (b"not an image", "image/png", "signature_mismatch"),
        (b"x", "application/pdf", "unsupported_mime"),
    ],
    ids=["empty", "oversize", "nul", "encoding", "image", "mime"],
)
def test_input_validation_before_network(data, mime, error):
    service = ObjectService()
    with pytest.raises(ValueError, match=error):
        GCSStorage("private-caseproof", session=service).put(data, mime)
    assert service.calls == []


def test_missing_remote_object_is_not_a_local_fallback():
    with pytest.raises(FileNotFoundError):
        GCSStorage("private-caseproof", session=ObjectService()).read("aa/" + "a" * 64)


def test_storage_selection_is_explicit_and_defaults_to_local(tmp_path, monkeypatch):
    from caseproof.adapters import storage
    from caseproof.adapters.local_storage import LocalStorage

    settings = Settings(_env_file=None, object_dir=tmp_path)
    assert isinstance(build_storage(settings), LocalStorage)
    settings.storage_backend = "gcs"
    with pytest.raises(ValueError, match="GCS_BUCKET"):
        build_storage(settings)
    settings.gcs_bucket = "private-caseproof"
    monkeypatch.setattr(storage, "GCSStorage", lambda bucket: ("gcs", bucket))
    assert build_storage(settings) == ("gcs", "private-caseproof")
    settings.storage_backend = "typo"
    with pytest.raises(ValueError, match="storage_backend"):
        build_storage(settings)
