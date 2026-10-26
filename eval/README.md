# Evaluation boundary

`backend_quality.py` scores frozen unfamiliar evidence; failures and provider errors
remain in the denominator. `backend_load.py` measures bounded concurrent work,
queue delay, retries and completion. `task_comparison.py` compares the same inputs
with a reference assembly process; field parity does not prove human time saved.

`run.py`, `replay.py`, `arms.py` and `metrics.py` retain earlier versioned experiment
harnesses. Predictions are written before scorer labels are read. Cached/live/mock
provider modes must stay explicit. Synthetic fixtures are not customer validation.
Historical raw results remain in the local archive; current verified scope is in
`docs/TESTING.md` and `docs/INTEGRATION_RESULTS.md`. The remaining unfamiliar-input
case N28 is deferred to actual Document AI evaluation; no further local OCR tuning
is claimed.
