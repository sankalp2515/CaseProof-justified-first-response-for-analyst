# CaseProof isolated package

**Current publication/restoration record:** [docs/SUBMISSION_VERIFICATION.md](docs/SUBMISSION_VERIFICATION.md). The chronological notes below retain earlier attempts and superseded availability states. The Clueso export has since completed; sampled output frames show real UI throughout. Public access has been restored, but full cloud acceptance remains blocked by Vertex spend-cap propagation at the recorded test time.

Release rerun: **380 backend tests passed** in the offline Linux test container using the current source/test trees; **88 frontend tests** and the production build passed. The initial submission package was pushed as `312b821` to `sankalp2515/CaseProof-justified-first-response-for-analyst`. Private runtime/media, credentials, learner profile and original checkout's held untracked files were excluded. Public Playwright acceptance submitted a fresh complaint but timed out waiting for assessment while Vertex reported a breached cap; it is not recorded as a passing end-to-end run.

## Technical package
This folder contains the existing CaseProof product and assets from source revision `ad92cef00c5670704f465c88ed2700f2f87d0406`, plus local integration changes. See `SOURCE_PROVENANCE.md`. This is not a claim that the application was newly authored through the installed curriculum.

Run from this folder after Docker Desktop's Linux engine is healthy:

```powershell
docker compose up --build -d --wait
```

Open http://127.0.0.1:8246/ . The default Compose project, network, image tags and volumes are isolated from the original package. No cloud deployment is performed. Existing cloud URLs in inherited documentation refer to the original deployment, not this package.

## Changes made here
- Retained the complete React/Vite application, landing assets, victim journey, analyst workspace, graph, requests, reviewer controls, report and follow-up implementation.
- Isolated local Compose project/network/images and default public port/base URL.
- Corrected AI source wording: response priority is not a recovery deadline, and observed balances are not established availability for recovery.
- Added bounded Windows atomic-file replacement retry, preserving atomic rename and surfacing persistent failures.
- Clarified the AI summary UI: citation and numeric consistency checks do not replace analyst review of meaning.
- Preserved original source attribution, licence and technical history references. No old Git history was rewritten or invented.
- Did not copy credentials, runtime databases, held untracked documents or local media.

## Verification performed in this folder
- Frontend: 87 tests passed across 26 files; production build passed.
- Targeted backend: 25 tests passed covering AI verification, cloud contracts and Firestore state.
- Compose configuration validation passed.
- Broader Windows-host backend suite: 369 passed, 4 failed, 5 skipped. Three failures require the unavailable Tesseract executable; one concurrent atomic-file-replacement test raises Windows PermissionError. The Windows replacement failure was then repaired with bounded retries; all five leadership tests passed on the focused rerun. Three OCR failures remain blocked by the unavailable executable; the canonical Linux-container regression has not run.

## Local runtime and acceptance — 26 October 2026
Docker Desktop recovered after the user started it. The isolated stack is healthy at http://127.0.0.1:8246/ . The canonical Linux regression passed **378 tests with no failures**, resolving the earlier host OCR/runtime blockers. The earlier failed host attempt remains recorded above.

Real Playwright acceptance passed **85 checks across two new complaints**. Both reached reviewer approval, both synthetic receiver acknowledgements, readable reports and persisted follow-up. Forty screen-state axe scans reported zero violations; no uncaught browser errors occurred. Automated scans do not establish complete manual WCAG conformance.

The separate complete tour passed **54 checks**, including delayed steps, reachable controls, sample generation, arrival alert, role handoff, delivery and ownership. Its browser error list is empty.

Compared 56 frontend source/public files against the incorporated archive, normalising CRLF/LF: only the deliberate AI verification wording in Gemini.jsx differs. CSS, layout, graph and assets are retained. Desktop overview and trail screenshots were inspected.

Evidence: `var/analyst-density/browser/acceptance.json`, `var/tour-validation/guided-results.json`, `var-regression.log`, `var-browser-acceptance.log`, `var-tour-acceptance.log`.

## Remaining acceptance
- Backend regression, two complete local workflows and the guided tour are verified above.
- Your hands-on review remains; use LOCAL_DEMO_GUIDE.md.
- Responsive and automated accessibility checks passed. Manual accessibility review and exported fullscreen video frames still need review when recording.
- Live Gemini processing was subsequently verified in the opt-in profile described below. The default profile still uses its explicit local provider.
- Learner review, public source publication, final human-written entry fields and accessible video are not complete. No public push or submission was performed.

Technical verification and competition eligibility are separate. This record does not certify submission eligibility or promise a prize.

## Live Gemini and recorded demonstration — 26 October 2026
The opt-in `compose.gemini.yaml` profile uses the Gemini Developer API, model `gemini-3.1-flash-lite`, image OCR and extraction with fallback disabled. The key is kept only in ignored `.env`. Existing local spending/call limits remain enabled. Original cloud services and original source worktree were not changed.

Added the missing local summary, investigation and image-reading API routes, preserving tenant checks and revision-bound summaries. Seven focused API tests passed. An HTTP-success/provider-unavailable response previously hid the summary completely; it now exposes the retry control. All **88 frontend tests** and the production build passed.

Case `CASE-030edbdd924d22f2` was created with fresh synthetic banking data and an uploaded PNG receipt. Recorded live Gemini OCR, extraction and cited summary; source inspection; bank-backed graph; actual customer request/reply; explicit additional-debit exclusion; disabled analyst approval; reviewer authorisation; both simulator acknowledgements; readable delivered report with money trace; persisted ownership and awaiting_external follow-up. No uncaught browser errors occurred. See `var/video-live/live-workflow-verification.json` for staged evidence.

This live run required resuming after Gemini 503 high-demand failures and a supported UI retry following cooldown. Those failures remain in the evidence. Do not claim uninterrupted provider availability. The narrated video shortens waits and resumes the same case; it does not substitute model responses or banking results. Earlier 85-check workflow and 54-check tour evidence used the default local provider, not this live profile. The video-specific capture did not perform additional axe scans.

The final Gemini-narrated export is 162.36 seconds, H.264 1920×1080/25fps with AAC audio. Exported frames were inspected for the summary, evidence, graph, reviewer and delivered report. Narration uses Gemini TTS, Charon. A media-only Clueso import bundle exists; no Clueso-produced version has been created because this chat has no callable Clueso editing tools despite an app permission record.

Public deployment remains blocked: the existing cloud frontend and API both have internal-only ingress and the public load-balancer URL returns 404. No ingress, IAM, deployment or cloud spending settings were changed. A successful local live-model recording does not establish public judge access.

## First-customer walkthrough revision
Reviewed the visual sequence of the supplied 221.42-second Veriscope reference and the organisers' official published review feedback. Captured the real landing-page entry with no browser errors and prepared a chronological 174-second screen-recording edit without repeated chapter bars. The revised twelve-part, 364-word narration explains controls and outcomes along the same supported journey. This version is silent editing footage, not a completed narrated video or a Clueso export. Only two new Gemini voice segments were generated before daily TTS quota errors; no quota or spending protection was changed.

Clueso version 2.0.1 is installed and enabled locally, but no Clueso tools were exposed to the active chat even after the user tagged the plugin. No Clueso project was created. Footage, script and editing brief are in ignored var/video-walkthrough/. The public GitHub main branch was audited: it is public but contains no files named scope.md, prd.md or spec.md. Local draft PRD/spec wording was corrected to describe the incorporated and verified implementation; these changes have not been published.

## Clueso project and export started
Clueso tools became available on the subsequent request. Listed the connected workspaces and projects, then obtained explicit confirmation to use sunita's Workspace. It initially had no projects. The source import project is 4be4d52e-4fb9-4f98-bdb4-ca04e4bcf63b; the final narrated project is 38d7c56d-9f50-4639-9524-ef5c9100dd1c at https://web.clueso.io/guide/38d7c56d-9f50-4639-9524-ef5c9100dd1c.

The final project contains twelve actual-video scenes, complete Clueso-generated Casual Mark narration and eleven restrained camera focus elements. Its timeline is about 154.82 seconds. Export 16dcbf8d-1124-4c66-b825-f9f77d10c6d6 was accepted at 1080p/30fps with captions. The export is not yet confirmed complete. Clueso still-frame preview rendering intermittently showed blank panels, including after replacing long footage references with short seekable scene files; individual frames also rendered successfully. Final MP4 playback QA is required before submission. Do not claim the blank-preview issue is resolved or the exported video is ready for judges. The tool instructed that the export appears in the editor's Exports tab and not to poll immediately after starting it.

Only product media and narration were uploaded; .env, browser session state and customer reply capabilities were excluded. No public publishing, plan upgrade or spending-protection change was performed.
