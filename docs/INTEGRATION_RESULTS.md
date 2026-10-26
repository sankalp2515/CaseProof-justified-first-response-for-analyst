## Live practice scenarios and full UI acceptance on staging — 17 October 2026

| Check | Result |
| --- | --- |
| Full browser acceptance against **staging** (`CASEPROOF_BASE_URL=https://8-233-217-230.sslip.io node frontend/scripts/acceptance-browser.mjs`) | **32/32 pass**, 10 accessibility scans with zero violations, zero page errors. Two new complaints with uploaded receipts, processed by `documentai` + `vertex` (live); request, customer reply, reviewer approval, both receivers sent, delivered report opened as a document |
| Same suite against the local stack | 32/32 pass (one earlier run timed out on a local queue backlog left by load tests; rerun passed) |
| Backend regression | 350/350 |
| Frontend unit/component tests | 49/49 |

Changes: testers choose when the scam happened (10 min, 40 min, 2 h ago) and every
session generates its own bank with distinct names, random amounts and money
movements timed to that choice; victim customers and the scam payment are marked;
the delivered report renders as a printable document. Cloud fixes found by running
the UI suite on staging: one-lane Cloud Tasks dispatch queued bank publications
ahead of complaints (now 5 lanes, worker up to 3 instances), and BigQuery aborted
concurrent multi-statement transactions (publication is now a single atomic
`MERGE`, verified live: duplicate deduplicated, changed digest rejected, 6
concurrent writes succeeded).

# Google staging validation — 17 October 2026

Deployed at the project owner's instruction to `caseproof-511713`, Mumbai
(`asia-south1`): **https://8-233-217-230.sslip.io**. Five Cloud Run services
(frontend, API, worker, simulator, scanner) behind one HTTPS load balancer with
Cloud Armor; Firestore, BigQuery, Cloud Storage quarantine/clean buckets, Cloud
Tasks, Cloud Scheduler, Document AI and Vertex AI Gemini. Synthetic data only.

| Check | Result |
| --- | --- |
| End-to-end through the public URL (`scripts/cloud_staging_check.py`) | **Pass, 226s**: practice session → victim complaint with the bank's own receipt PNG → Document AI OCR (9 lines) + Gemini extraction (`documentai`/`vertex`, mode `live`) → analyst request sent, customer link redirected and answered → extra debit explicitly marked unrelated → scheduled bank refresh → `COMPLETE_CANDIDATE` → reviewer `COMPLETE_HANDOFF` → both receivers `sent`, case `completed` (`CASE-f245810a08acdd31`) |
| Guided tour on the live site | All 46 steps found and spotlighted their targets; victim chapter auto-advanced; live golden-hour countdown shown (25:39 remaining on the tour case); no error banners |
| Ingress | API and frontend return 404 when called directly (load balancer only); worker, simulator and scanner return 403 to anonymous callers |
| Scanner | Private `/health` OK, ClamAV 1.4.6, fresh signatures |
| Practice personas | Contract tests: no cookie → 403; admin/unknown persona → 403; another tenant's case unreachable |
| BigQuery SQL | Every statement dry-run against real BigQuery (`scripts/bigquery_dry_run.py`) |
| Regression on the deployed code | 348/348 backend tests (offline `test` image); 48/48 frontend tests; tour dialog axe scans zero violations |
| Terraform | Remote state in `gs://caseproof-511713-tfstate`; 3/3 mocked plan tests; final applies changed only images and policies, nothing destroyed |

Real-service issues found and fixed during deployment (none were visible to
offline service doubles): Cloud Armor regex capture groups; BigQuery `STRUCT`
aliases; dotted Document AI version IDs; Vertex `429` retry budget; Gemini thinking
tokens truncating JSON; Gemini abbreviating long citation IDs (now short aliases
mapped back deterministically); daily model-call cap too low for judging; frontend
not waiting on asynchronous practice-bank publication. Details: [deployment record](DEPLOYMENT.md).

Not yet exercised on staging: Firestore contention under concurrent reviewers, Cloud
Tasks recovery after a forced worker failure, WAF blocking mode (still preview),
Google staff sign-in (practice personas are used instead), the retained unfamiliar
inputs (N28, manual O/0 receipt) through Document AI, and sustained load. One case
was reprocessed from a developer machine with the same configuration while
diagnosing failures; all recorded passes ran on the deployed services.

## Local validation — microservice stack, 17 October 2026

The application now runs as independent Compose services on one `caseproof`
network: `frontend` (nginx + React), `api`, `worker`, `ocr`, `trail-feed`,
`simulator`, plus the one-shot `preload`. Only `frontend` publishes a port
(127.0.0.1:8080). The earlier single supervised container was retired; its case
volume (`caseproof_application-data`) was reused, and the simulator/feed SQLite
files were copied into their new per-service volumes. Preserved manual case
`CASE-418e861b3fda9010` remains readable with its follow-up state.

| Check | Result | Scope |
| --- | --- | --- |
| Full backend regression | 325/325 pass, 201s | `test` image, offline; adds scanner, pool, connection-reuse and API-host tests |
| Frontend unit/component suite | 39/39 pass | 14 test files |
| Automated browser full workflow | 30/30 pass, 56s | Through the `frontend` service; two new complaints with uploaded PNGs |
| Accessibility scans | 10 scans, zero reported violations | Victim, queue, overview, trail and delivery screens |
| Fault injection (`recovery-check`) | Pass | OCR outage gives `LOCAL_OCR_ERROR` with no OCR facts, then retry succeeds; worker SIGKILL mid-job has its lease reclaimed; all six services restarted with revision, digest, audit and evidence hash unchanged |
| Terraform | fmt, validate, 2/2 mocked deployment-hold plans | No apply |
| Cloud frontend image | Builds; routes checked | `/customer/{token}` gives a relative 303 to the reply route; `/v1`, `/health`, `/inspector` return 404 (the load balancer sends them to the API); build fails without a staff client ID |

## Scanner latency gate (closed)

Root cause: every scan ran `clamscan`, which reloads the whole signature set.
The scanner now loads one resident `clamd` engine at startup and streams evidence
over a private Unix socket. Measured with `check_scanner.py` at 1 CPU / 2 GiB:

| Configuration | Engine load (once) | Clean text | Clean PNG | EICAR |
| --- | --- | --- | --- | --- |
| Previous per-scan `clamscan` | — | 63–90s | 63–93s | 61s; 120s timeout under load |
| Resident engine, idle | 77s | 0.02s | 0.02s | 0.01s |
| Resident engine, 4 busy CPUs | 83s | 0.27s | 1.26s | 0.05s |
| Hardened parsers, idle | 32s | 0.02s | 0.07s | 0.01s |
| Hardened parsers, 4 busy CPUs | 55s | 0.99s | 0.04s | 0.01s |

Service level: 16 concurrent `/scan` uploads of the retained receipt PNG (8 at a
time) were all clean, max 1.8s; resident memory 1.0 GiB of 2 GiB. Cloud Run:
startup CPU boost on, request concurrency 4, startup probe allows 250s. Cold
starts still pay the one-time engine load; consider `min_instance_count = 1`
during staging. Logs: `var/readiness/scanner-clamd/`.

## Practice bootstrap (B11)

Causes: each practice world opened and locked the shared bank store about 30
times; DuckDB probed for the absent `pandas` module on every parameterised query
(about 2,400 failed imports and 12,000 filesystem stats per world); the worker
rebuilt bank ingestion (schema DDL under the bank lock) every 3 seconds. Fixes:
re-entrant per-thread bank connection, cached module absence, ingestion built
once, and a pool of three pre-built practice worlds claimed atomically.
`eval/practice_bootstrap.py` (10 sequential + 10 at concurrency 5, running stack):

| Stage | Idle sequential median / p95 | Idle concurrent p95 | 4-CPU load sequential p95 | 4-CPU load concurrent p95 |
| --- | --- | --- | --- | --- |
| Before | 5.7s / 8.2s | 51.4s | 25.1s | 79.4s |
| Connection reuse + import fix | 3.4s / 10.6s | 21.9s | 12.8s | 42.6s |
| + worker ingestion fix | 1.7s / 3.2s | 19.7s | 10.8s | 30.6s |
| + pre-built pool | 1.0s / 2.2s | 17.8s | 14.5s (pooled claims 0.14s) | 17.9s |

The 20-session bursts exhaust the 3-world pool, so burst figures mostly measure
on-demand generation. Reports: `var/readiness/b11/`.

## Sustained capacity (local, bounded)

`eval/backend_load.py http --sizes 5,10,15 --repetitions 2 --sessions 3`: 60
complaints, each with a real uploaded receipt, OCR, worker processing and audit
checks, 120s per-complaint budget. All 60 passed; zero failed jobs, retries or
duplicate publications; 315s total on an 8-CPU host.

| Concurrent complaints | p50 | p95 |
| --- | --- | --- |
| 5 | 13.7–15.1s | 20.5–23.0s |
| 10 | 28.0–34.3s | 45.5–54.7s |
| 15, one worker | 50.9–71.0s | 76.3–95.3s |
| 15, two workers (`--scale worker=2`) | — | 54.5–57.3s |

One worker processes jobs serially, so latency grows linearly with burst size.
Job leases made a second replica safe (zero duplicates); background polling is not
yet partitioned across replicas (backlog). Reports: `var/readiness/capacity-*`.

Local results above predate the Google deployment; see the staging section for
the cloud results. No production readiness or human time-saved claim.

## Earlier single-container validation — 17 October 2026 (superseded topology)

The application runs as one supervised `caseproof-app-1` container at localhost
port 8080. Both previous six-service stacks are stopped, with volumes preserved.
A new persistent volume starts with bank records and zero complaints.

| Check | Result | Scope |
| --- | --- | --- |
| Frontend unit/component suite | 39/39 pass | 14 test files |
| Focused host/supervisor/worker tests | 5/5 pass | Route isolation, valid/expired capabilities, cleanup, heartbeat |
| Clarification return-target contract | 2/2 pass after reproduced failure | Both local and cloud adapters |
| Automated browser full workflow | 30/30 pass | Two new complaints with actual uploaded PNGs |
| Accessibility scans | 10 scans, zero reported violations | Sampled victim, queue, overview, trail and delivery screens |
| Browser uncaught errors | Zero | Automated acceptance run |
| Full local backend regression | 316/316 pass, 1340.61s | Windows source mounts; zero failures/skips |
| Published-snapshot CI | 319/319 backend; 39/39 frontend pass | Clean Ubuntu checkout; includes the three later-added regressions |
| Static/config checks | Scoped Ruff and configured mypy pass; Compose parses | No cloud apply |
| Credential-pattern review | 523 text files, no matches | Limited signatures; not an exhaustive secret audit |

## Browser workflow exercised

Both fresh automated cases select a preloaded synthetic account/payment, submit
an actual bank-generated PNG plus a new narrative, wait for real local OCR,
appear automatically in the analyst queue, render a money trail, send a missing
information request, accept the victim's response, explicitly exclude an unrelated
candidate debit, and enforce reviewer-only approval. Both report destinations
acknowledge delivery. Follow-up owner/next action survives reload.

Cases: `CASE-bdf18f757cf33080` and `CASE-7ec653d3f2c43046`.
Provider: real local Tesseract plus literal extraction rules. No live cloud model
or pre-recorded complaint outcome is represented.

Manual browser testing independently verified the entry screen, empty practice
queue, account/payment selection, narrative entry, receipt download/file upload,
and creation of `CASE-418e861b3fda9010` with both evidence items received.
After recovering the Chrome extension connection, the manual flow also completed:
analyst reviewed the brief and requested clarification; the victim replied,
explicitly excluded the unrelated INR 10,500 candidate, and recorded inability to
supply a clearer receipt. Local OCR left the original receipt unassociated
(including a payee O/0 mismatch), so the reviewer approved **escalation with gaps**
at revision 30. Both simulators acknowledged it; owner and follow-up next action
persisted through reload. Later observation updates created a new revision that
requires its own review; the original delivered packet remains inspectable.
Retained input: `eval/corpora/manual_integration_v1/receipt-56000.png`.
Screenshot: `var/integration-manual/reports-delivered.png` (local evidence).

## Confirmed issues fixed during integration

1. A hung initialization process could escape supervisor cleanup. It now remains
   tracked until exit, has a 300s deadline, and is killed/reaped on failure.
2. Customer reply envelopes omitted their case return target. Both local/cloud
   capability-validated responses now include scoped `case_id`; red tests failed
   before the fix. The first browser run's return-navigation timeout is retained.
3. SPA hosting preserves API 404s, denied expired links, no-store/no-referrer,
   request limits and same-origin session cookies rather than a generic fallback.

An additional code-review pass found no remaining confirmed code publication
blocker after fixes. This is an engineering review, not an independent security
certification. Runtime image: `sha256:99789878f49f26d0925ef23df2f185469a5536603ea4d44ab7e915a1f027bb65`.

Raw local reports: `var/frontend-validation/quality/acceptance.json`, screenshots
and `axe-results.json`; `var/readiness/integrated-backend-full.xml`. Published-snapshot CI:
https://github.com/sankalp2515/CaseProof/actions/runs/39013953399 (passed).
The original failed attempt is preserved in the same local evidence directory.

## Remaining boundaries

Scanner competing-load latency, native dependency risk assessment, B11 bootstrap
latency and N28 unfamiliar-input quality remain open. Real Google service, IAM,
WAF and Document AI/Vertex acceptance needs an authorized staging deployment.
No production readiness or human time-saved claim. Google deployment remains held.
