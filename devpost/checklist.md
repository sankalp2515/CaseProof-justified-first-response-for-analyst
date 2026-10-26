# CaseProof — Verification checklist

This checklist records verification of the incorporated implementation. It does not backdate development, commits or curriculum reviews.

- [x] Source provenance, license and component origin retained.
- [x] Isolated local Compose runtime with no credentials required by default.
- [x] Canonical Linux backend regression: 378 tests passed in the recorded local run.
- [x] Frontend regression after integration fixes: 88 tests and production build passed.
- [x] Local real-browser acceptance: 85 checks, two new complaints, both receiver acknowledgements and persisted follow-up.
- [x] Separate complete local guided tour: 54 checks, no uncaught browser errors.
- [x] Forty automated screen-state axe scans: no reported violations; manual WCAG conformance is not established.
- [x] Live Gemini local run: uploaded receipt, OCR/extraction/summary, source inspection, graph, clarification, independent review, both deliveries and report output. Provider 503 failures required cooldown and supported retry.
- [x] Narrated Clueso export: 154.854 seconds, 1080p; sampled frames show actual UI. Watermark remains; full audio/caption timing review is outstanding.
- [ ] Restored public cloud journey verified end to end after shutdown.
- [ ] Final human video review and permanent public video link.
- [ ] Competition entry fields and eligibility independently checked before submission.
- [ ] Real analyst pilot and production banking/security/identity validation.

See [current verification](../docs/SUBMISSION_VERIFICATION.md), [scope](../scope.md), [requirements](../prd.md), [technical specification](../spec.md) and [demo guide](../LOCAL_DEMO_GUIDE.md).
