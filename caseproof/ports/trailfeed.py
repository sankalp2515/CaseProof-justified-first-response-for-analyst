"""Boundary for simulated downstream bank updates; Pub/Sub can replace JSON."""

from typing import Protocol


class TrailFeedPort(Protocol):
    def load(self, as_of: str) -> list[dict]: ...
