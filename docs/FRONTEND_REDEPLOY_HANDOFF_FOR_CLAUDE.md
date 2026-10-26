# CaseProof frontend integration: Claude pre-redeploy handoff

## Scope and current status

The redesigned frontend is integrated into the **main worktree**, `E:/Codex Projects/CaseProof`, on `main`. This document is a test-and-review handoff, **not authorisation to redeploy**. No image push, Terraform apply, DNS change, live-cloud mutation or launch-flag change was performed during integration.

Starting main commit: `896a8a9`. Source worktree: `codex/landing-demo-journey`, through `a637291`. The four feature commits were cherry-picked, rather than merging the old snapshot of deployment files:

| Source | Main integration commit | Contents |
|---|---|---|
| `d757065` | `0c50d06` | Landing page; synthetic evidence; receipt/priority information; downloadable handoff. |
| `973ba26` | `b7de54e` | Guided intake; reference-style alert; Cases register; realistic practice identifiers; layout repairs. |
| `3115f4a` | `a6e8a2f` | Stable notifications; tour restart/loading; responsive header; favicon; role/referral explanations. |
| `a637291` | `abb78fd` | Honest record of the earlier incomplete repeat-run test. |

Later integration fixes preserve main's current scenario model and are recorded in the final integration commit and `FRONTEND_MAIN_INTEGRATION_VALIDATION.json`. Independent review also identified and fixed duplicate-ID provisional amount inflation and provider-specific fallback wording.

**Read the final validation receipt before claiming tests passed.** Earlier `LANDING_DEMO_VALIDATION.json`, `UX_REPAIR_VALIDATION.json` and `SESSION_2026_10_18_VALIDATION.json` describe the source-worktree snapshots. They are useful history, not evidence that this combined main snapshot has passed a live cloud run.

## Features retained from the newer main worktree

- Existing Gemini summary, evidence reader and intake assistant, with server-side source checks.
- The readable two-part delivered report (`PacketDocument.jsx`) and its print/raw-data controls.
- First-visit/expired-practice handling and plain-language API errors.
- Scenario timing choices: **10 minutes, 40 minutes, 2 hours**. Each fresh session receives independent randomized bank records.
- Six scenario networks with twelve distinct customers: **six marked scam victims and six normal customers**. The normal customers remain available under Other customers; do not assume every account has the scenario debit.
- Tenant separation, HTTP-only victim cookies, Origin checks, role checks, revision/digest approval checks, bounded retries and cloud staff authentication configuration.
- Existing infrastructure, Cloud Run build configuration, root Compose service separation and deployment scripts.

The main worktree had unrelated uncommitted documentation/media work. Its 22 starting files were hashed and backed up under ignored `var/frontend-main-integration/preserved/`; the integration verifies they remain byte-for-byte unchanged. Do not include that unrelated work in a frontend integration commit without its owner's agreement.

## Integrated visual and workflow changes

1. `/` serves the designed landing page; `/app/` serves React. Landing links open reporting, staff and the guided tour. Static assets use `/app/landing/...`; both pages use `/app/favicon.svg`.
2. Reporting supports real PNG/JPEG/UTF-8 text uploads and labelled synthetic receipt/chat/call-log images. Sample financial fields come from the selected server-owned payment. Samples do not create bank transactions or downstream observations.
3. Victim completion links directly to the exact complaint in the analyst workspace. Payments are newest first. A reported first-contact time after a payment requires explicit acknowledgement; it never resets bank-timed urgency.
4. The golden-hour popup shows backend facts for a new/current urgent complaint. Role switching, routine processing transitions, Queue/Cases navigation and reload no longer create duplicate arrivals. Read state is per browser session, and visible alerts are filtered to the active practice queue.
5. Queue prioritises current work. Cases is a history register with delivery information. Both can open a complaint; they are different screens.
6. The twelve-highlight tour begins at the reporting entrance. Global Tour always restarts at the introduction, including after minimising. It clears guide progress/case association, **not** bank records or a report draft. The user must explicitly choose Start a fresh practice session to create a fresh clock/catalogue.
7. Tour loading guidance handles delayed real responses. The footer remains reachable on narrow and short viewports. Case-specific steps do not silently select another queue case.
8. Analyst header/avatar, search, Requests spacing and the narrow case-summary grid are repaired. Main's Gemini, scenario and report styles are retained alongside those fixes.
9. Reviewer-only authorisation remains enforced. Both roles can inspect evidence/trail/history. The role guide and urgent-referral example explain the workflow.
10. Practice sample receipts use a consistent embedded sans font and wider line spacing. An integration run exposed a lost dotted-payee prefix in monospaced OCR; actual pixel regressions now cover that handle and three others without weakening bank matching or readiness.
11. Historical packet downloads include exact approved revision/digest and sourced trail positions/paths. The interactive graph remains in the workspace. The existing readable report also remains available.
12. Local simulator observations refresh near the 15-minute freshness boundary (840 seconds), instead of every 120 seconds; new complaints still get immediate coverage and failed refreshes back off. Actual new evidence, observations and clock expiry can still legitimately trigger Processing/review and invalidate approval.

## Provider truth: do not repeat the old disclaimer

**Deployed staging uses Google Document AI and Vertex AI Gemini.** The existing live run is recorded in `docs/INTEGRATION_RESULTS.md`. This integration does not roll it back or substitute a local provider in deployment configuration.

The isolated **local** regression stack deliberately uses Tesseract/local rules and synthetic receiver services, so its recorded provider must say that. A local pass does not verify a new cloud image. Conversely, local provider records do not mean deployed Gemini is unavailable. Google staff sign-in, institutional bank integration and Gemini processing are separate capabilities.

## Backend and frontend must be released together

This is **not a frontend-only release**. The redesigned UI additionally uses:

- `GET /v1/ui-config`
- `GET/POST /v1/victim/sample-evidence`
- Extended victim complaint receipt: initial bank-timed priority, artifact upload/processing details.
- `GET /v1/cases/{case_id}/delivered-packets/{packet_id}/document`

These exist in both local and cloud APIs in the integrated main source. Keep existing `/genai/...` and `/v1/victim/intake-assist` endpoints too. Inspect the running OpenAPI before testing: a frontend against an old backend can otherwise fail with 404s. Prompt/assets are under `caseproof/` and copied by the existing backend Dockerfiles; the practice renderer uses Pillow's embedded font without downloading runtime fonts.

When a later redeployment is authorised, build **both backend and frontend from the same final tested commit**. The current practice deployment build uses `FRONTEND_PROFILE=cloud` and `STAFF_ACCESS=practice`; preserve the configured access profile. Do not silently switch it to staff Google sign-in or change Google credentials.

`scripts/redeploy_staging.sh` **pushes images and applies Terraform**. Do not use it as a test command. Similarly, do not submit `infra/google/cloudbuild.yaml` just to run offline checks: it includes publication/release artifacts.

## Repeatable offline checks (PowerShell)

From `E:/Codex Projects/CaseProof`:

```powershell
git status --short
git log -6 --oneline
git diff --check

Push-Location frontend
npm ci --no-audit --no-fund
npm test -- --reporter=dot
npm run build
Pop-Location

& .\.venv\Scripts\python.exe -m pytest `
  tests/flow/test_demo_evidence.py `
  tests/flow/test_google_backend_contract.py `
  tests/flow/test_judge_session.py `
  tests/unit/test_demo_scheduler.py `
  tests/unit/test_handoff_document.py `
  tests/unit/test_literal_timezone.py `
  tests/unit/test_practice_pool_age.py `
  tests/unit/test_sample_receipt_pixels.py `
  tests/unit/test_practice_payee_extraction.py `
  tests/unit/test_realistic_practice_handles.py `
  tests/unit/test_genai_verification.py `
  tests/unit/test_frontend_host.py -q -rs
```

The Google contract tests use in-process service doubles; label them accurately. The pixel OCR unit test can skip on Windows without Tesseract; verify real OCR in the Linux service/browser run. Do not install a second conflicting OCR runtime just to suppress that skip.

## Isolated local UI/backend test stack

Do not rebuild/restart the deployment or another chat's stack. A new helper prepares a **separate** project `caseproof-predeploy`, fresh project volumes, and loopback port **8198**. It does not start anything until Compose is explicitly run. It mounts this main checkout and built frontend read-only and uses already-installed local runtime images; it does not retag or push images.

Prerequisites: local Docker images `caseproof-api:local`, `caseproof-ocr:local`, `nginx:1.28-alpine`; current `frontend/dist` from the build above. If runtime dependencies changed, validate/build a separately tagged image and update the generated test configuration; do not overwrite another stack's runtime image tag.

```powershell
& .\.venv\Scripts\python.exe scripts/frontend_predeploy_stack.py
docker compose -p caseproof-predeploy -f var/frontend-main-integration/compose.json up -d --no-build
docker compose -p caseproof-predeploy -f var/frontend-main-integration/compose.json ps --all
Invoke-RestMethod http://127.0.0.1:8198/health
Invoke-RestMethod http://127.0.0.1:8198/ready
```

Wait for preload to exit 0 and API/worker/frontend to start. The helper uses `PRACTICE_POOL_SIZE=0` so an idle prebuild does not compete with checks. Source mounts on Windows can be slower than the immutable production images. Keep one origin throughout; the victim and staff must share their browser context/cookies.

Then run the real browser checks sequentially, to avoid unnecessary contention:

```powershell
$env:CASEPROOF_BASE_URL = 'http://127.0.0.1:8198'
Push-Location frontend
node scripts/acceptance-browser.mjs
node scripts/guided-ux.mjs
# Optional: verify the original packet for a case created by this local run.
$env:CASEPROOF_CASE_ID = '<new completed case ID from acceptance.json>'
node scripts/session18-output.mjs
Remove-Item Env:CASEPROOF_CASE_ID
Pop-Location
Remove-Item Env:CASEPROOF_BASE_URL
```

These checks create real synthetic complaints and use the real local worker/OCR/receivers. They do not fabricate successful API responses. The acceptance suite repeats with another **marked scam victim**, records missing-information states and delivery, and verifies role-switch notification deduplication. The guided suite follows all twelve highlights. Outputs are under `var/frontend-validation/quality/` and `var/ux-repair/`; check timestamps because earlier failed receipts can remain beside successful ones.

Do not run the historical `session18-regressions.mjs` unmodified on an empty new stack: it deliberately references the case/hostname from the original repair session. Its generic assertions are already described here and notification checks are included in the main acceptance script.

The test stack can be stopped with `docker compose -p caseproof-predeploy -f var/frontend-main-integration/compose.json stop`. Preserve its data for review. Do not use `down -v`, remove database volumes, or reset the main checkout.

## Manual acceptance: any new supported complaint

1. Open the landing page. Check fonts, no missing assets, favicon, keyboard focus, staff/report links and Take the guided tour.
2. Choose 10 minutes and Start a fresh practice session. Confirm the queue starts empty. Select a customer **marked with a suspicious payment**; the Other customers section contains ordinary accounts intentionally. Do not hard-code Samer or a fixed ₹ amount.
3. Select the marked payment. Initially provide a genuinely incomplete narrative such as “I noticed this suspicious transfer and need the fraud desk to investigate.” Leave unknown authorisation/contact details unknown. Upload the actual bank PNG receipt or supported original evidence. Also exercise synthetic sample generation and each file-kind selector.
4. Submit once. Confirm upload/extraction states remain distinct and the report opens its exact analyst case. In an already open queue, verify the golden-hour alert shows the server-selected amount and bank-timed urgency.
5. Dismiss/read the alert; switch Analyst → Reviewer → Analyst repeatedly, visit Cases and return, then reload. Notifications must not multiply or reopen the dismissed arrival.
6. Review the brief, source lines, bank match, distinct additional debit, Money Trail and Next best step. New evidence may still be processing. Inspect the actual provider provenance. Verify main's AI summary/evidence/intake panels handle supported/unavailable states without blocking the case workflow.
7. Review/send an actual proposed clarification. Open the scoped reply link in the same test browser, answer the question and submit. Confirm a new revision and changed next action. Confirm or deny the additional debit explicitly.
8. As Analyst, reviewer approval/export must be denied. As Reviewer, review current revision/digest with a reason. An urgent referral and a complete packet have separate eligibility; never bypass missing facts or reuse stale approval.
9. Send approved content and wait for **both distinct** receiver acknowledgements. Queued export and a single acknowledgement are not delivery.
10. Switch to Analyst, save owner/next action and awaiting-external follow-up. Reload; inspect Audit, approval history, original delivered report, JSON and downloaded handoff HTML. Print to PDF and confirm the delivered revision/digest and trail paths are preserved.
11. Repeat with another marked victim and then a 2-hour scenario. The latter must display elapsed urgency without making a supported report impossible. Test an ordinary customer separately: do not invent a trail when bank evidence does not support one.
12. Test tour restart from step 4, minimise/reopen, Back after validation errors, a delayed real server response, 390/574px victim/header views, 768px tablet and 1242/1440px staff views. Check Requests padding, search/identity alignment, graph overflow, long text, loading/error/empty states, keyboard operation and visible footer controls. Run axe and record limitations; a zero-violation scan is not a full accessibility certification.

## Release gates and limits

- No unresolved merge markers, missing assets, unhandled browser exceptions or unexplained failing tests.
- Preserve and review the final current-main validation receipt; do not claim a historical worktree run validates the combined main release.
- Run the complete new-complaint/clarification/reviewer/both-receivers flow on the candidate images. Staging live Gemini/scanner/staff-auth acceptance remains a later authorised step.
- Retain failures, timeouts, skipped tests and model/provider limits. Local repeat-run delays were observed previously; do not promise “without any error” from a build alone.
- Both providers and bank destinations must be labelled truthfully. A delivered synthetic packet is not a real freeze, refund, regulatory submission or closed investigation.
- Stop before push/apply/redeploy until the release owner authorises that stage. Do not change `deployment_enabled`, `dispatch_enabled`, `frontend_backend_tests_passed`, WAF/CORS/Origin checks, auth principals or queues/Scheduler as part of frontend testing.

## Copyable Claude task

Read this handoff and `docs/FRONTEND_MAIN_INTEGRATION_VALIDATION.json`. Review the integrated main commit, preserve unrelated dirty files, and run the offline and real-browser checks against a separate local candidate stack. Verify both backend and frontend contracts, fresh complaint repeatability, Gemini feature preservation, the twelve-step tour, duplicate-alert prevention and the original handoff document. Record actual pass/fail/skip results with provider and commit provenance. Fix any verified regression without reverting the latest main features. Stop before redeploying, pushing images or applying infrastructure, and report remaining blockers explicitly.

## Results on the integrated main source (18 October)

- **64 frontend tests passed**, 21 files; production build passed.
- **34 affected backend tests passed**. Four pixel variants skip on the Windows host without Tesseract; **all four separately passed through the real Linux OCR service**, preserving full payee, IST time and the absent-reference limitation. One pre-existing Starlette TestClient deprecation warning remains.
- **36 real-browser acceptance assertions passed**, covering two fresh complaints, actual PNG/OCR, targeted request/reply, candidate-debit decisions, independent reviewer authorisation, both acknowledgements, readable delivered report, saved ownership, reload and notification deduplication. Cases: `CASE-11e818a2c839bae2`, `CASE-6f8ccfd365822832` on the isolated 8198 stack.
- **35 guided-journey assertions passed**, all twelve highlights, actual sample images, reviewer decision, both receipts and follow-up; see the receipt for its newly generated case ID.
- **4 document checks passed**: original approved identity, sourced trail paths, both receivers for that revision and printable PDF. Files: `var/session-18/handoff.html`, `handoff.pdf`, `handoff-document.png`.
- **13 sampled axe scans reported zero violations** across the repeated acceptance and guide; no uncaught browser errors. This does not certify complete accessibility.
- Targeted Ruff checks passed. Existing infrastructure, cloud Dockerfiles, main Compose service layout and the 22 pre-existing dirty files were preserved.
- The supplementary full Linux suite was stopped after no test output was observed during the slow source-mount run; it is **not counted as passing**. Run the full offline suite on freshly built candidate images before release.

The first guide run exposed the cropped receipt's OCR prefix loss and correctly blocked complete approval. The pixels were repaired, not the financial/readiness guard. The final guide passed. A Windows output-path error and an API-startup race in the document helper were also repaired; final document checks passed. These earlier failures remain in logs and are not disguised as successful runs.

This integration's functional browser tests used actual **local** processing and receivers. The deployed Gemini integration is retained, but the new combined cloud image has not been deployed or live-tested by this task. Claude must not remove the remaining release gates based only on these results.
