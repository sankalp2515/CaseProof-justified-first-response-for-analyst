"""Private GCS evidence storage with content checks and create-only writes."""

import re
from hashlib import sha256
from urllib.parse import quote

import google.auth
from google.auth.transport.requests import AuthorizedSession

from caseproof.adapters.object_validation import validate_evidence, validate_object_key


class GCSStorage:
    def __init__(self, bucket, *, session=None):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket or ""):
            raise ValueError("GCS_BUCKET must name a private configured bucket")
        self.bucket = bucket
        if session is None:
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/devstorage.read_write"]
            )
            session = AuthorizedSession(credentials)
        self.session = session

    def put(self, data, mime_type):
        key, digest = validate_evidence(data, mime_type)
        response = self.session.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o",
            params={"uploadType": "media", "name": key, "ifGenerationMatch": 0},
            data=data,
            headers={"Content-Type": mime_type},
            timeout=45,
        )
        if response.status_code == 412:
            # Concurrent/repeated upload: verify existing bytes rather than overwrite.
            self.read(key)
        else:
            response.raise_for_status()
        return key, digest

    def read(self, key):
        validate_object_key(key)
        response = self.session.get(
            f"https://storage.googleapis.com/storage/v1/b/{self.bucket}/o/{quote(key, safe='')}",
            params={"alt": "media"},
            timeout=45,
        )
        if response.status_code == 404:
            raise FileNotFoundError(key)
        response.raise_for_status()
        data = response.content
        if sha256(data).hexdigest() != key.split("/")[1]:
            raise ValueError("corrupt_object")
        return data
