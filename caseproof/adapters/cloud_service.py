"""OIDC-authenticated calls to explicitly configured private Cloud Run services."""

from urllib.parse import urlparse

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token


class CloudService:
    def __init__(self, origin, *, session=None, token=None, timeout=20):
        parsed = urlparse(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".run.app")
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
        ):
            raise ValueError("Explicit private Cloud Run HTTPS origin required")
        self.origin = origin.rstrip("/")
        self.session = (
            session if session is not None else httpx.Client(timeout=timeout, trust_env=False)
        )
        self.token = token

    def post(self, path, *, json=None, content=None, mime=None, key=None):
        if path not in {"/scan", "/case_ticket", "/cfcfrms_report_update", "/urgent_referral"}:
            raise ValueError("Unknown private service action")
        credential = self.token() if self.token else id_token.fetch_id_token(Request(), self.origin)
        headers = {"Authorization": "Bearer " + credential}
        if mime:
            headers["Content-Type"] = mime
        if key:
            headers["Idempotency-Key"] = key
        response = self.session.post(
            self.origin + path, json=json, content=content, headers=headers
        )
        response.raise_for_status()
        return response.json()
