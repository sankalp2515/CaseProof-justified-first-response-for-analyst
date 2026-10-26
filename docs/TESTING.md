# Validation

## Automated tests

```sh
# Canonical local OCR/backend regression environment (offline, `test` target)
docker compose --profile validation run --rm tests

# Equivalent without Compose (as CI runs it)
docker build -t caseproof-tests .
docker run --rm --network none -e DATA_DIR=/tmp/tests -e SQLITE_URL=sqlite:////tmp/tests/cases.db -e DUCKDB_PATH=/tmp/tests/bank.duckdb -e OBJECT_DIR=/tmp/tests/objects -e LLM_PROVIDER=gemini -e LLM_MODE=live -e CUSTOMER_PORTAL=false caseproof-tests python -m pytest -q --basetemp=/tmp/pytest -o cache_dir=/tmp/pytest-cache

# Frontend unit and component tests (Node 24)
cd frontend
npm ci
npm test
npm run build
```

With the complete application running, use `node frontend/scripts/acceptance-browser.mjs`
from the repository root after installing Playwright Chromium. It submits new
complaints with uploaded PNGs and exercises requests, replies, review, delivery,
follow-up and responsive/accessibility checks. Results are local under `var/`.
`CASEPROOF_BASE_URL` overrides the default `http://127.0.0.1:8080`.

Stack-level checks (stack running):

```sh
# Fault injection: OCR outage, worker kill, restart of every service (mounts the Docker socket)
docker compose --profile validation run --rm --no-deps recovery-check
# Practice-session bootstrap latency
python -m eval.practice_bootstrap http://127.0.0.1:8080
# Scanner acceptance on the exact scanner image (resident engine, timings)
docker build -f Dockerfile.scanner -t caseproof-scanner .
docker run --rm --network none --cpus 1 --memory 2g caseproof-scanner python check_scanner.py
```

`scripts/validate-local.ps1` runs build, start, regression, browser acceptance and
fault injection in sequence. The capacity harness runs inside the test image on
the Compose network:
`docker run --rm --network caseproof -e API_BASE_URL=http://frontend:8080 caseproof-tests:local python -m eval.backend_load http --corpus eval/corpora/novel_v1 --output /tmp/load --sizes 5,10,15`.

## Recorded baseline before frontend consolidation

- Full packaged backend: 313 passed, zero failures/skips.
- Separate prepared cloud runtime: 25 complaint/security contracts passed.
- Terraform deployment-hold mocked plans: 2 passed.
- Final scanner native retry: clean text/PNG, EICAR detection and missing/stale
  signature rejection passed. Scans took 63–88s; an initial 120s competing-load
  timeout was retained. Superseded by the resident-engine scanner (see results).

Google service responses and identity signature verification are explicit doubles
in offline contracts. These tests do not measure live Document AI/Gemini quality,
real Google IAM, human time saved, or production bank integration.

Microservice-stack validation: 325 backend tests, 39 frontend tests, 30 browser
checks, fault injection, scanner/B11/capacity measurements. Earlier integrated
package: 316 local backend tests, CI 319 backend, and a complete manual
escalation/delivery flow. Details: `docs/INTEGRATION_RESULTS.md`.
Retain failed attempts and limitations alongside rerun results.
