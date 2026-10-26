# Submission build and verification

Current release record: **26 October 2026**. The source, plans, runtime profiles and demonstration must be assessed together. A successful local recording does not establish public cloud availability.

**27 October recovery:** The owner approved a Vertex cap of INR 3,000. Billing confirms it and the unchanged INR 5,000 Cloud Run cap are CONFIGURED. A direct live Gemini request returned `OK`, and a complete public browser workflow passed **51 checks**, including reviewer approval and both delivery acknowledgements. Thirty axe scans reported zero violations; no uncaught browser errors occurred. The earlier INR 2,000 enforcement and failed attempts remain described below as recovery history, not current availability. See [public acceptance evidence](SUBMISSION_CLOUD_ACCEPTANCE.json).

## Product and source

The submission package contains the complete CaseProof React/Vite application, Python workflow backend, synthetic banking services, evidence processing, independent review, report delivery and follow-up. The [scope](../scope.md), [PRD](../prd.md) and [specification](../spec.md) describe this implementation. [Source provenance](../SOURCE_PROVENANCE.md) identifies the incorporated team-owned application; new publication does not rewrite its development history.

## Verified local behavior

| Verification | Result and limits |
| --- | --- |
| Canonical Linux backend release regression | **380 passed**, zero failures, in 345.26 seconds. Runs offline in the canonical Linux test image with this package's current `caseproof/` and `tests/` mounted read-only. Two warnings: upstream TestClient deprecation and the expected oversized-image safety test. |
| Frontend release regression | 88 tests passed across 26 files; production build passed. |
| Default local workflow | 85 browser checks across two new complaints, including both synthetic receiver acknowledgements and persisted ownership. |
| Guided tour | Separate complete run: 54 checks, no uncaught browser errors. |
| Accessibility | Forty screen-state axe scans reported zero violations in the recorded local acceptance. This is not a certification of complete manual WCAG conformance. |
| Live Gemini profile | Real Gemini Developer API image reading, extraction and cited summary; source inspection, graph, customer clarification, explicit debit exclusion, reviewer approval, both deliveries, readable report and persisted follow-up. Twenty-six distinct recorded checks; no uncaught browser errors. |
| Provider resilience | The live recording required cooldown and supported retry after Gemini 503 failures. Waits were shortened in editing; successful outputs were not fabricated. |

The default local profile uses Tesseract/rules. The recorded live profile uses `compose.gemini.yaml`, `gemini-3.1-flash-lite`, no fallback, and server-side credentials. The separate cloud profile uses Document AI and Vertex Gemini. Banks, feeds and receiving institutions are synthetic in all profiles.

## Video

The initial Clueso export is **154.854 seconds**, H.264 1920×1080 with AAC audio. A revised **167.05-second** export has been requested with a sharper opening, explicit analyst outcome and a new real invalid-amount validation/cancellation scene; its playback QA is pending. It starts on the landing page and follows one case through victim reporting, analyst work, clarification, reviewer approval, report delivery and ownership. Samples every five seconds show actual UI throughout; no persistent blank scenes were observed. Full narration/caption timing review and the permanent public video URL remain outstanding. The export includes a Clueso watermark.

The recording uses the local live-Gemini profile. It does not claim to be a capture of the separately restored cloud deployment. It visibly shows meaningful outputs and role boundaries. The revised project now includes an actual invalid-amount check after the delivered output; provider-error recovery remains documented separately rather than fully demonstrated in this short video.

## Existing cloud service restoration

Public origin: **https://8-233-217-230.sslip.io/**. It had intentionally been stopped by restricting ingress and pausing background dispatch. Recovery preserved the HTTPS load balancer, Cloud Armor, IAM-authenticated worker/scanner/simulator, instance/concurrency limits, durable data, processing queue and reconcile scheduler. Minimum instances remain zero, so a first request can cold-start.

The first attempts submitted real complaints but could not finish while Vertex returned `403 Spend cap breached`. The INR 2,000 cap re-enforced; the owner then explicitly approved INR 3,000. Both current service caps are CONFIGURED, not left lifted. These are separate service caps, not an account-wide ceiling. No billing-route switch was used.

After billing recovery, the application still held a temporary 403 provider circuit for up to 24 hours. The worker was recycled. API recycling exposed another blocker: its old backend image digest had been deleted from Artifact Registry. The previous serving revision remained in place while recovery proceeded.

Rebuilt the backend from the published, locally tested source and deployed the same immutable digest to API, worker and simulator:

`sha256:471aca8ef895b0dd7cdb6448732cc6195841e14b7555650cd22926c2750fccc8`

Ready revisions: API `caseproof-api-00024-9wx`, worker `caseproof-worker-00023-862`, simulator `caseproof-simulator-00020-mt5`. No Terraform apply, permission broadening, database reset or volume deletion occurred. Frontend/scanner retained their existing images; full image/source identity for those unchanged deployments is not asserted.

**Public end-to-end acceptance passed:** one new practice complaint with PNG receipt, live Document AI OCR and Vertex `gemini-3.5-flash` extraction, analyst arrival alert, source citation, graph, actual scoped customer reply and reassessment, explicit unrelated-debit exclusion, analyst approval denial, reviewer approval, both synthetic receiver acknowledgements, readable delivered report and persisted owner/awaiting-external follow-up. Fifty-one checks passed; 30 screen-state axe scans reported zero violations; no uncaught browser errors. See [machine-readable evidence](SUBMISSION_CLOUD_ACCEPTANCE.json). Provider availability can still change; one passing run does not guarantee uninterrupted service.

This is separate from the recorded local walkthrough. The earlier complete guided-tour test was local, not a claim that this public run exercised every tour step.

References: [Google spend-cap behavior](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps), [API cap update sequence](https://docs.cloud.google.com/billing/docs/how-to/budget-api-spend-cap).

## Repository hygiene

The publication excludes `.env`, private learner profile, browser sessions/cookies, customer-reply capabilities, runtime databases, Terraform state/variables and private recordings. An exact staged-content scan found no configured local credentials or high-confidence API/private-key patterns. Held untracked documents/media from the original checkout were not imported. The source license is retained.

The initial public package is commit `312b821`. GitHub CI runs independently of the local results; an in-progress CI run is not a completed pass. New verification updates are committed separately from the initial publication.

## Reproduce the local checks

```sh
docker build -t caseproof-tests .
docker run --rm --network none -e DATA_DIR=/tmp/tests \
  -e SQLITE_URL=sqlite:////tmp/tests/cases.db \
  -e DUCKDB_PATH=/tmp/tests/bank.duckdb -e OBJECT_DIR=/tmp/tests/objects \
  -e LLM_PROVIDER=gemini -e LLM_MODE=live -e CUSTOMER_PORTAL=false \
  caseproof-tests python -m pytest -q --basetemp=/tmp/pytest -o cache_dir=/tmp/pytest-cache
cd frontend
npm ci --no-audit --no-fund
npm test
npm run build
```

The offline regression uses test-controlled provider adapters; it does not claim live Gemini calls. For real browser acceptance, start the default local stack and run `frontend/scripts/analyst-workspace-browser.mjs` with `CASEPROOF_BASE_URL=http://127.0.0.1:8246`. It creates new synthetic complaints and saves private test evidence under ignored `var/`. The optional live profile must be tested separately with supported retries; fixed provider timing is not guaranteed.

## Remaining release checks

1. Public cloud processing and full handoff passed as recorded above; retain capacity and monitor existing budget alerts during judging.
2. Backend now uses the tested package. Frontend/scanner retain their earlier images; do not infer complete image/source identity for unchanged deployments.
3. Final human review of narration, captions, readability and watermark; upload the video to the required public host.
4. Complete entry fields and event-specific eligibility/curriculum checks. Technical verification does not substitute for those requirements.
5. Production identity, real bank integrations, operational/compliance review and practitioner outcome measurements remain outside the synthetic prototype.

For a reusable click-by-click workflow, follow [LOCAL_DEMO_GUIDE.md](../LOCAL_DEMO_GUIDE.md).
