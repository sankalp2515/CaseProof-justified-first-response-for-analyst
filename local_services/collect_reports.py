"""Collect measured Docker outputs; never synthesize a missing validation result."""

import shutil
from pathlib import Path


def main():
    target = Path("/data/validation")
    target.mkdir(exist_ok=True)
    for name in (
        "local_validation.json",
        "local_scenarios.json",
        "local_scenario_summary.json",
        "local_recovery_validation.json",
    ):
        source = Path("/data") / name
        if source.exists():
            shutil.copy2(source, target / name)
    source = Path("/browser")
    if source.exists():
        for file in source.iterdir():
            if file.suffix in {".json", ".png"}:
                shutil.copy2(file, target / file.name)
    print("Copied measured reports and browser screenshots to /data/validation")


if __name__ == "__main__":
    main()
