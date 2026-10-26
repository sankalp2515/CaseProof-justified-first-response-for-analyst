"""Prepare an isolated local check of the integrated source and built frontend.

Does not start services, build/push images, call cloud APIs, or change deployment.
Uses existing local runtime images with this checkout mounted read-only.
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-port", type=int, default=8198)
    args = parser.parse_args()
    if not 1024 <= args.web_port <= 65535:
        parser.error("web port must be between 1024 and 65535")
    root = Path(__file__).resolve().parents[1]
    if not (root / "frontend/dist/index.html").is_file():
        parser.error("Build frontend/dist first with npm run build")
    folder = root / "var/frontend-main-integration"
    folder.mkdir(parents=True, exist_ok=True)
    config = folder / "nginx.conf"
    config.write_text(
        (root / "frontend/docker/local.conf.template")
        .read_text(encoding="utf-8")
        .replace("${CASEPROOF_API_UPSTREAM}", "api:8000"),
        encoding="utf-8",
    )
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
        "PRACTICE_POOL_SIZE": "0",
        "PUBLIC_BASE_URL": f"http://127.0.0.1:{args.web_port}",
    }
    source = root.as_posix() + ":/app:ro"
    common = {
        "image": "caseproof-api:local",
        "init": True,
        "environment": env,
        "volumes": [source, "application-data:/data"],
    }
    services = {
        "preload": {
            **common,
            "command": ["python", "-m", "local_services.preload"],
            "depends_on": {
                name: {"condition": "service_started"}
                for name in ("ocr", "trail-feed", "simulator")
            },
        },
        "api": {
            **common,
            "depends_on": {"preload": {"condition": "service_completed_successfully"}},
        },
        "worker": {
            **common,
            "command": ["python", "-m", "local_services.worker"],
            "depends_on": {"preload": {"condition": "service_completed_successfully"}},
        },
        "ocr": {"image": "caseproof-ocr:local"},
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
            "volumes": [source, "feed-data:/data"],
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
            "volumes": [source, "receiver-data:/data"],
        },
        "frontend": {
            "image": "nginx:1.28-alpine",
            "init": True,
            "ports": [f"127.0.0.1:{args.web_port}:8080"],
            "volumes": [
                (root / "frontend/dist").as_posix() + ":/usr/share/nginx/html/app:ro",
                config.as_posix() + ":/etc/nginx/conf.d/default.conf:ro",
            ],
            "depends_on": {"api": {"condition": "service_started"}},
        },
    }
    target = folder / "compose.json"
    target.write_text(
        json.dumps(
            {
                "name": "caseproof-predeploy",
                "services": services,
                "volumes": {
                    name: {} for name in ("application-data", "feed-data", "receiver-data")
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(target)
    print(f"Local test URL: http://127.0.0.1:{args.web_port}")


if __name__ == "__main__":
    main()
