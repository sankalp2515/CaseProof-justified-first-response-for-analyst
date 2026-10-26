# CaseProof synthetic evaluation kit

This is a **fictional testing environment**, not the CaseProof AI application and not a real bank. It contains 48 cases in 12 scenario families, 172 artifact files, a 48-record fictional bank ledger, a loopback-only support console and an offline scorer. No Gemini calls, real customer data, payment functionality or government integration are included.

## Dataset card

- Generation date: 12 October 2026. Deterministic seed: 20261012.
- Cases CP001-CP016: development, four families. CP017-CP036: reserved held out, five families. CP037-CP048: safety challenge, three families.
- Four variants share each family template. Amounts, dates and identifiers vary, but these are correlated examples, not 48 independent observations.
- Fictional brand: Cedar Bank. Names have a Demo suffix; accounts and references are explicitly synthetic; payees use `.invalid` addresses.
- Formats: readable receipt PNGs, message PNGs, narratives and clarifications in TXT; one deliberately blurred receipt family. No real logos or copied bank screens.
- Three examples contain mixed Hindi and English. Rendered Hindi examples are provided for inspection, not a validated language benchmark.
- Labels are authored from the generator, not adjudicated by a fraud operations expert. Obtain an independent domain review before making bank-workflow validation claims.
- Scope: complaint evidence intake. The dataset is not for estimating fraud prevalence, detecting real transactions, determining liability or predicting fund recovery.
- Reserved held out status relies on operator discipline. Authors can see the full kit; it is not an independently collected or secret benchmark. Do not tune prompts on its labels.

## File boundaries

`inputs/CPxxx.json` lists initial evidence and metadata. `fixtures/CPxxx/initial` contains initial artifacts. `fixtures/CPxxx/followup` contains response artifacts; these must not be in the initial model context. `private_gold` contains answer labels, stage outcomes and expected source text/coordinates. **Never serve or attach private_gold or case_index.csv to the model.** `case_index.csv` contains expected actions for a human reviewer and must be treated as labels, despite its convenient location.

`artifact_manifest.json` records hashes and byte counts. `policy/demo_policy_v1.json` is a demonstration policy, not a bank or NCRP SOP. The government portal's separate identity requirements are not implemented here.

## Run the local support console

Use Python 3.12 or later. The supplied utilities use only the Python standard library; no API key is required.

```powershell
python mock_server.py --port 8765
```

Open `http://127.0.0.1:8765` in a browser. The server binds only to loopback. Do not deploy it as a production service. Its sessions and ticket state are in memory, shared by local viewers, and cleared on restart. It has no production identity, tenant isolation, persistent storage or safety certification.

The console loads initial evidence, lets you ask a permitted simulated question, and reveals a response only when the seeded customer has one for that question. It also displays an optional fictional institution ledger. Give every evaluation arm the same ledger access if it is used; a customer-only arm must not receive hidden bank context.

Creating a fictional support ticket requires a human approval checkbox, a positive revision number and an explicit complete or escalation disposition. Ticket IDs start with SYNTH and are not official complaint acknowledgements. The simulator checks basic fields but **does not implement CaseProof's revision or readiness engine**. The future application must enforce those rules before calling it.

### Local API contract

| Route | Purpose |
| --- | --- |
| GET /health | Confirms synthetic mode and that AI is not implemented |
| GET /catalog | Case IDs and family metadata, without expected actions |
| GET /case?id=CP001 | Initial artifact metadata and request catalogue |
| GET /artifact?case=CP001&id=CP001-R | Allowed artifact bytes, no arbitrary file paths |
| POST /reveal | `{ "case_id": "CP009", "request_id": "request_reference_crop" }`; reveals simulated response if available |
| GET /case?id=CP009&stage=followup | Followup metadata only after reveal |
| GET /ledger?id=CP001 | Optional explicitly fictional institution record |
| POST /tickets | Test handoff; requires Idempotency-Key header and approved case metadata |
| GET /tickets | In-memory fictional ticket records |
| POST /reset | Clears local simulation state |

Production bank adapters are not specified by these endpoints. No permission to access bank, NPCI, police, NCRP or CFCFRMS APIs is implied.

## Scoring future implementation outputs

The scorer **does not run the application or model**. Export predictions for each arm separately. For every case, record the initial stage and, where a valid response was obtained, the after_followup stage. Missing stages remain in the denominator. A failed followup does not disappear from the report.

A record looks like this (illustrative schema only, not a measured result):

```json
{
  "case_id": "CP017",
  "stage_id": "initial",
  "failed": false,
  "fields": { "amount_minor": null, "currency": "INR", "date": "2026-10-01", "transaction_reference": "SYNTH-TX-0017" },
  "next_request_ids": ["clarify_amount"],
  "required_fact_ids_present": ["amount", "date", "transaction_reference", "deception_account"],
  "disposition": "REVIEW_REQUIRED",
  "forbidden_requests": [],
  "critical_failures": []
}
```

`fields` represents settled extracted values, not the list of all conflicting claims. Expected null means unresolved, not a guessed value. Fact presence means the relevant source observations were recognized; it is **not proof of resolved completeness**. Preserve contradictions in the application and use the separate disposition check.

```powershell
python evaluate.py --predictions predictions_C.jsonl --split heldout --output results_C.json
```

The scorer checks exact normalized fields, top one request on actionable stages, appropriate no-request stages, available required fact coverage, disposition and reported critical flags. It cannot independently detect every hallucination, privacy failure, prompt injection or unsupported claim. Manually review source support, request burden and packet correctness; instrument timing, costs and every sequential request in the application. Do not infer that zero reported flags means production safety.

Compare A adaptive deterministic checklist, B Gemini extraction plus that checklist, and C full CaseProof. Use identical initial evidence and followup availability. A static ask-everything checklist can be an additional illustration, not the only comparison. Keep model, prompts, policy version and run timestamp. Never generate results by reading the gold answers into the system under test.

## Integrity checks

```powershell
python verify_kit.py
python -m unittest test_kit.py -v
```

The checks verify counts, family splits, source file hashes, label structure and scorer failure accounting. Utility self-tests are not CaseProof accuracy results. No prediction or model-result file is prefilled in this kit.

With the server running on port 8765, use `python -m unittest test_mock_api.py -v` for the four API checks. These tests reset all local simulation state before and after each check. The ten utility tests do not require a running server. The scorer rejects case/stage predictions outside the selected split rather than silently ignoring them.

## Licensing and permissions

All fictional data and visual artifacts were newly generated for this package. No third-party customer dataset or bank branding is redistributed. Proposed public-release licenses are CC0 1.0 for synthetic fixtures and MIT for utility code, **subject to the human team's license decision before publication**. No license to real institution data or government automation is granted. Refer to third-party service terms and dependency licenses when implementing the application. Fonts are rendered into images; no font files are distributed.

## Scope of verification

The accompanying package verification report describes the actual local checks performed. It distinguishes fixture integrity, utility behavior and local UI inspection from the unimplemented cloud product and unrun model benchmark. Do not convert utility test pass counts into impact claims.
