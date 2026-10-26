# Submission build and verification

Current release record: **26 October 2026**. The source, plans, runtime profiles and demonstration must be assessed together. A successful local recording does not establish public cloud availability.

## Product and source

The submission package contains the complete CaseProof React/Vite application, Python workflow backend, synthetic banking services, evidence processing, independent review, report delivery and follow-up. The [scope](../scope.md), [PRD](../prd.md) and [specification](../spec.md) describe this implementation. [Source provenance](../SOURCE_PROVENANCE.md) identifies the incorporated team-owned application; new publication does not rewrite its development history.

## Verified local behavior

| Verification | Result and limits |
| --- | --- |
| Canonical Linux backend regression | Earlier complete run: 378 passed. A release regression including subsequent route fixes is recorded below when complete. |
| Frontend release regression | 88 tests passed across 26 files; production build passed. |
| Default local workflow | 85 browser checks across two new complaints, including both synthetic receiver acknowledgements and persisted ownership. |
| Guided tour | Separate complete run: 54 checks, no uncaught browser errors. |
| Accessibility | Forty screen-state axe scans reported zero violations in the recorded local acceptance. This is not a certification of complete manual WCAG conformance. |
| Live Gemini profile | Real Gemini Developer API image reading, extraction and cited summary; source inspection, graph, customer clarification, explicit debit exclusion, reviewer approval, both deliveries, readable report and persisted follow-up. Twenty-six distinct recorded checks; no uncaught browser errors. |
| Provider resilience | The live recording required cooldown and supported retry after Gemini 503 failures. Waits were shortened in editing; successful outputs were not fabricated. |

The default local profile uses Tesseract/rules. The recorded live profile uses `compose.gemini.yaml`, `gemini-3.1-flash-lite`, no fallback, and server-side credentials. The separate cloud profile uses Document AI and Vertex Gemini. Banks, feeds and receiving institutions are synthetic in all profiles.

## Video

The Clueso export is **154.854 seconds**, H.264 1920×1080 with AAC audio. It starts on the landing page and follows one case through victim reporting, analyst work, clarification, reviewer approval, report delivery and ownership. Samples every five seconds show actual UI throughout; no persistent blank scenes were observed. Full narration/caption timing review and the permanent public video URL remain outstanding. The export includes a Clueso watermark.

The recording uses the local live-Gemini profile. It does not claim to be a capture of the separately restored cloud deployment. It visibly shows meaningful outputs and role boundaries; invalid-input and provider-error recovery are tested elsewhere rather than fully demonstrated in this short video.

## Existing cloud service restoration

The existing public origin is **https://8-233-217-230.sslip.io/**. It had intentionally been stopped by restricting ingress and pausing background dispatch. At the owner's instruction, this release restored:

- Frontend/API ingress through the existing HTTPS load balancer, retaining the direct-ingress restriction and Cloud Armor.
- IAM-authenticated worker, scanner and simulator ingress; no public invoker permissions were added to those services.
- The existing processing queue and reconcile scheduler.
- The existing instance/concurrency limits. Minimum instances remain zero; first-use cold starts can take time.

No service images were rebuilt, no Terraform was applied, and no data/volumes were deleted. The current cloud images therefore remain a separately deployed build; local source-image parity is not inferred.

The public landing page and `/health` returned **HTTP 200** after restoration. A real Playwright run started a fresh practice session and submitted a new PNG-evidence complaint. No uncaught browser errors occurred, but assessment did **not** finish within the test window: Vertex returned **403 PERMISSION_DENIED: Spend cap breached**.

Billing now reports the explicitly approved **₹2,000 Vertex AI cap as CONFIGURED** and the existing **₹5,000 Cloud Run cap as CONFIGURED**. Google documents that service recovery after lifting an enforced cap can take up to one hour. Neither cap was left lifted. These are separate service caps, not an account-wide spending ceiling; other cloud costs and the existing alert budget remain.

**Public end-to-end acceptance is not yet passed.** After the billing block clears, verify actual processing, current-version reviewer approval, both acknowledgements and the delivered document before sharing the deployment as a fully working judge demo. Do not create repeated complaints to bypass a provider error or label a queued job successful.

References: [Google spend-cap behavior](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps), [API cap update sequence](https://docs.cloud.google.com/billing/docs/how-to/budget-api-spend-cap).

## Repository hygiene

The publication excludes `.env`, private learner profile, browser sessions/cookies, customer-reply capabilities, runtime databases, Terraform state/variables and private recordings. An exact staged-content scan found no configured local credentials or high-confidence API/private-key patterns. Held untracked documents/media from the original checkout were not imported. The source license is retained.

## Remaining release checks

1. Public cloud processing and full handoff after Vertex billing recovery; record the actual result.
2. Confirm cloud image/source parity if deploying the new package later. Restoring access alone is not a redeployment.
3. Final human review of narration, captions, readability and watermark; upload the video to the required public host.
4. Complete entry fields and event-specific eligibility/curriculum checks. Technical verification does not substitute for those requirements.
5. Production identity, real bank integrations, operational/compliance review and practitioner outcome measurements remain outside the synthetic prototype.

For a reusable click-by-click workflow, follow [LOCAL_DEMO_GUIDE.md](../LOCAL_DEMO_GUIDE.md).
