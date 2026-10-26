from typing import Protocol


class OutboundPort(Protocol):
    def send(self, kind: str, payload: dict, idempotency_key: str) -> dict: ...
