"""One-shot synthetic bank preload for the Compose stack. Never creates a complaint."""

from caseproof.config import Settings
from caseproof.pipeline.orchestrator import Orchestrator
from local_services.demo_world import DemoWorld


def main():
    # Idempotent: an existing volume keeps its records, cases and approvals.
    DemoWorld(Orchestrator(Settings(_env_file=None))).ensure()
    print("Synthetic bank records ready; no complaint was created", flush=True)


if __name__ == "__main__":
    main()
