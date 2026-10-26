# CaseProof local demonstration

## Start
From this folder, with Docker Desktop running Linux containers:

```powershell
docker compose up -d --wait
```

Open **http://127.0.0.1:8246/**. The application, API, worker, OCR and synthetic bank/receivers run in this folder's isolated Compose project. `docker compose stop` stops this project without deleting its cases. Do not delete volumes to restart a demonstration.

## One fresh golden-hour case
1. Use the landing page's reporting/tour entry. Select **10 minutes ago**, start a fresh practice session and choose a customer with a suspicious payment.
2. Report a payment scam. Select the relevant suspicious debit, describe the bank-impersonation/safe-account incident and keep unrelated payments unselected.
3. Attach a supported image/text file or explicitly labelled practice sample. Follow the upload limits shown on screen. Each sample button generates its own attachment; wait for processing rather than submitting duplicate clicks.
4. Review and submit. Note the new case reference. The acknowledgement confirms intake; scanning/extraction and assessment may still be running.
5. Use the labelled analyst-demo handoff. The same browser keeps the victim and analyst views in the same practice session.
6. Inspect the golden-hour alert, top response window, confirmed disputed amount, separate candidate amount and recommended next action. Switching roles is not a new complaint and must not add an arrival notification.
7. Open **Evidence**. Select a finding and compare its quoted original and any image highlight. An extracted detail is not automatically a bank-confirmed fact.
8. Open **Money Trail**. Follow the selected disputed debit, inspect account/transfer source and observation time, and try Replay. The graph shows reported movements and balances, not a freeze or recovery.
9. Open **Requests**. Send the currently proposed relevant clarification. Use its customer reply link, answer the actual question and submit. Reassessment should produce a new version. Do not assume the question will be identical for every complaint.
10. Explicitly confirm or exclude any additional debit through the customer view. For the demonstrated safe-account case, an unrelated debit should be excluded if that is the fictional customer's answer.
11. Return to **Review & decision**. Analyst approval remains disabled. When full readiness is supported, use the visible reviewer-demo handoff, inspect current findings/gaps and enter a reason. Approve the current version in its confirmation dialog. If a conflict occurs, reload and review again.
12. Open **Delivery & follow-up** and review/send the approved reports. Wait for **both** receiver acknowledgements. Queued or partially delivered packets are not complete delivery.
13. Open **View delivered report**. Inspect the investigation brief, payments, sources and **Where the money was traced**. The readable document records the approved version.
14. Return to analyst, set an owner and concrete next action, save follow-up and reload to verify persistence. Delivery completes a handoff; the investigation remains open for external responses.

## Tour
The complete tour was tested separately through the same real workflow. Minimise it when it covers a control; restore it after completing the page action. Wait for actual readiness before advancing. Use its fresh-start/restart controls rather than assuming an old step applies to a new case.

## Urgent referral
Urgent referral is a separately assessed, limited transaction referral. It can be eligible while the full investigation still has missing information. It requires its own reviewer decision and must not be presented as a completed full report.

## Processing profile and limits
The default profile uses real Tesseract OCR and explicit extraction rules, with synthetic bank/feed/report services. The optional live profile was verified using Gemini image reading, extraction and a cited summary:

```powershell
docker compose -f compose.yaml -f compose.gemini.yaml up -d --wait
```

This requires a local ignored `.env` containing `GEMINI_API_KEY`. It uses `gemini-3.1-flash-lite`, with fallback disabled and call limits enabled. Gemini returned intermittent 503 high-demand errors during recording. Allow its cooldown, then use **Retry current failed job** on Evidence, or **Retry summary** for a summary failure. Do not repeatedly submit complaints to work around an existing job failure. A fresh practice session creates newly timed bank data; an old case's response clock continues to elapse.

The recorded live case completed customer clarification, reviewer approval, both synthetic deliveries, the readable report and persisted follow-up. The original cloud deployment is separate. Current restoration and public-access results are recorded in docs/SUBMISSION_VERIFICATION.md; local verification does not prove public access. Provider labels must reflect actual execution; never describe local fixture or rule output as a live model response.

Use fictional information only. Do not share customer-reply capability URLs, session cookies or credentials in screenshots, logs or public packages. A new complaint can have different amounts, graph structure, request or readiness; follow the current server-supported next action instead of forcing a memorised result.
