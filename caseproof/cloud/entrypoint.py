"""Explicit cloud component entrypoint; does not provision or seed anything at import."""

import os

from caseproof.config import Settings

s = Settings(_env_file=None)
component = os.environ.get("CLOUD_COMPONENT", "api")
if s.runtime_backend != "google":
    raise ValueError("Cloud entrypoint requires RUNTIME_BACKEND=google")
if component == "simulator":
    from caseproof.cloud.simulator import create_app

    app = create_app(s)
elif component in {"api", "worker"}:
    from caseproof.cloud.app import create_app

    app = create_app(s, worker=component == "worker")
else:
    raise ValueError("Unknown cloud component")
