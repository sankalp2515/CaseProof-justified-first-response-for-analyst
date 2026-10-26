"""Local HTTP feed transport; downstream update validation stays identical."""

import httpx

from caseproof.adapters.local_trail_feed import validate_updates


class HTTPTrailFeed:
    def __init__(self, url):
        self.url = url

    def load(self, as_of: str) -> list[dict]:
        result = httpx.get(
            self.url + "/v1/updates", params={"as_of": as_of}, timeout=10, trust_env=False
        )
        result.raise_for_status()
        return validate_updates(result.json(), as_of)
