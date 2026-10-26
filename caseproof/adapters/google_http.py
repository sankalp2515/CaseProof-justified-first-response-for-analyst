"""Bounded Google REST transport using attached identity; no private keys."""

import google.auth
from google.auth.transport.requests import AuthorizedSession


def authorized_session():
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(credentials)
