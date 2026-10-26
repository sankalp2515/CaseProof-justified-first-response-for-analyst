import json
from pathlib import Path
from typing import Any


def load_policy(
    path: Any = Path(__file__).resolve().parents[2] / "policy/demo_policy_v2.json",
) -> dict:
    """Load the deterministic request and readiness policy from the package."""
    p = json.loads(Path(path).read_text(encoding="utf-8"))
    if p["score_formula"] != "3R+2C+U+A-2E-3P":
        raise ValueError("unsupported formula")
    return p
