import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / "var/journey-validation"
folder.mkdir(parents=True, exist_ok=True)
env = {
    "RUNTIME_BACKEND": "local",
    "DATA_DIR": "/data",
    "SQLITE_URL": "sqlite:////data/cases.db",
    "DUCKDB_PATH": "/data/bank.duckdb",
    "OBJECT_DIR": "/data/objects",
    "TRAIL_FEED_URL": "http://trail-feed:8000",
    "LOCAL_OCR_URL": "http://ocr:8000",
    "MOCK_SERVICES_URL": "http://simulator:8000",
    "LOCAL_SERVICE_HOSTS": '["simulator","ocr","trail-feed"]',
    "LLM_PROVIDER": "local",
    "LLM_MODE": "local",
    "EXTERNAL_WORKER": "true",
    "CUSTOMER_PORTAL": "true",
    "PRELOADED_DEMO": "true",
    "PRACTICE_POOL_SIZE": "1",
    "PUBLIC_BASE_URL": "http://caseproof-journey.localhost:8188",
}
common = {
    "image": "caseproof-api:local",
    "init": True,
    "environment": env,
    "volumes": [str(root).replace("\\", "/") + ":/app:ro", "journey-data:/data"],
}
services = {
    "preload": {**common, "command": ["python", "-m", "local_services.preload"]},
    "api": {
        **common,
        "ports": ["127.0.0.1:8184:8000"],
        "depends_on": {"preload": {"condition": "service_completed_successfully"}},
    },
    "worker": {
        **common,
        "command": ["python", "-m", "local_services.worker"],
        "depends_on": {"preload": {"condition": "service_completed_successfully"}},
    },
    "ocr": {"image": "caseproof-ocr:local", "ports": ["127.0.0.1:8186:8000"]},
    "trail-feed": {
        "image": "caseproof-api:local",
        "command": [
            "python",
            "-m",
            "uvicorn",
            "local_services.feed:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--no-access-log",
        ],
        "environment": {"DATA_DIR": "/data", "TRAIL_FEED_PATH": "/data/feed.json"},
        "volumes": ["journey-feed:/data"],
    },
    "simulator": {
        "image": "caseproof-api:local",
        "command": [
            "python",
            "-m",
            "uvicorn",
            "mock_services.bank_mock:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--no-access-log",
        ],
        "environment": {"DATA_DIR": "/data"},
        "volumes": ["journey-receivers:/data"],
    },
}
for service in ["preload", "api", "worker"]:
    services[service].setdefault("depends_on", {}).update(
        {s: {"condition": "service_started"} for s in ["ocr", "trail-feed", "simulator"]}
    )
(folder / "compose.json").write_text(
    json.dumps(
        {
            "name": "caseproof-journey",
            "services": services,
            "volumes": {"journey-data": {}, "journey-feed": {}, "journey-receivers": {}},
        },
        indent=2,
    )
)
print(folder / "compose.json")
