from typing import Protocol


class IdentityPort(Protocol):
    def actor(self, user_id: str): ...
