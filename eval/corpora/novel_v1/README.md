# Frozen novel-input corpus v1

Frozen before the first execution on 16 October 2026. `SHA256` commits the exact
`corpus.json` bytes; each asset's hash is recorded in that JSON. Oracles come from
the synthetic bank inputs and renderer parameters, never extracted app output.
Do not edit the corpus to improve a score. New inputs require a new corpus ID.

30 authored cases: five independently rendered receipt layouts crossed with clean,
wrong amount, blank image, embedded instruction, unrelated image and two selected
payment conditions. Both PNG and JPEG occur; dates use ISO conventions, amounts
use INR/Rs and identities use the prototype's synthetic formats. Fonts/layouts
vary modestly. This is not a representative real-bank document/language sample.

First execution: `var/readiness/novel-v1-first`. Repairs: separately named regression
directories. Later runs are regression, never unseen evaluation. Case-level and
field-level failures stay in their denominators; explicit provider errors do not
disappear. Source-support checks validate quoted OCR/text, not pixel transcription
truth. Exact pixel-field oracles supply a separate accuracy measure.

With OCR running on the Compose network, run inside the application image:

```
python -m eval.backend_quality run --corpus /app/eval/corpora/novel_v1 --output /app/var/readiness/<new-run>
python -m eval.backend_load ocr --corpus /app/eval/corpora/novel_v1 --output /app/var/readiness/<new-run>
python -m eval.backend_load http --corpus /app/eval/corpora/novel_v1 --output /app/var/readiness/<new-run>
```

Prefer the built image with only a host reports directory mounted (for example,
`/reports`); use a new output directory for each run. HTTP load
uses actual gateway/API/worker services and a fresh practice account catalogue.
It creates new complaints, uploads images and repeats submission IDs to verify
idempotency; it never replays a pre-created complaint. For persisted queue metrics,
mount `caseproof-local_state` read-only at `/data` and set
`JOBS_METRICS_DB=/data/caseproof.db`. It only reads that DB for telemetry.

Quality exit status is nonzero when any exact-field or guard check fails. That is
expected for the retained v1 OCR limitations; do not suppress the failing status.
Frozen timestamps remain historical; this corpus does not measure live urgency or
freshness over arbitrary later execution dates. Dedicated clock/freshness tests
cover those rules. No live Gemini or human time-saving result is claimed.
