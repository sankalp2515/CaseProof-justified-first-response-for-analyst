"""Shared model-call reservations and cache; filesystem caches are not cloud quotas."""

import time
import uuid
from datetime import datetime, timezone

from caseproof.adapters.llm_cache import CacheMiss, CallCapError
from caseproof.domain.contracts import hash_json


class FirestoreLLMCache:
    def __init__(self, settings, documents):
        self.s, self.documents = settings, documents

    def key(self, provider, model, prompt, inputs):
        return hash_json(
            {
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "inputs": inputs,
                "schema": "v1",
            }
        )

    def peek(self, provider, model, prompt, inputs):
        row = self.documents.get("model_cache/" + self.key(provider, model, prompt, inputs))
        if row and row.get("status") == "done":
            row["result"]["run"]["mode"] = "cache"
            return row["result"]
        return None

    def call(self, case_id, provider, model, prompt, inputs, fn):
        key = self.key(provider, model, prompt, inputs)
        owner, day = uuid.uuid4().hex, datetime.now(timezone.utc).date().isoformat()
        case_path, daily_path = "model_limits/" + hash_json(case_id), "model_limits/day-" + day

        def reserve(tx):
            cached = tx.get("model_cache/" + key)
            if cached and cached.get("status") == "done":
                cached["result"]["run"]["mode"] = "cache"
                return cached["result"]
            if self.s.llm_mode == "cache_only":
                raise CacheMiss("response not cached")
            if cached and cached.get("until", 0) > time.time():
                raise CallCapError("model_call_in_progress")
            case, daily = tx.get(case_path) or {"count": 0}, tx.get(daily_path) or {"count": 0}
            if case["count"] >= min(24, self.s.llm_max_calls_per_case) or daily["count"] >= min(
                5000, self.s.llm_daily_call_cap
            ):
                raise CallCapError("LLM call cap reached")
            for path, counter in ((case_path, case), (daily_path, daily)):
                counter["count"] += 1
                tx.set(path, counter)
            tx.set(
                "model_cache/" + key,
                {"status": "reserved", "owner": owner, "until": time.time() + 180},
            )
            tx.set(
                "model_calls/" + owner,
                {
                    "case_id": case_id,
                    "day": day,
                    "provider": provider,
                    "model": model,
                    "status": "reserved",
                },
                create=True,
            )
            return None

        hit = self.documents.transact(reserve)
        if hit:
            return hit
        start = time.perf_counter()
        try:
            data, usage = fn()
            result = {
                "data": data,
                "run": {
                    "mode": "live",
                    "provider": provider,
                    "model_id": model,
                    "prompt_hash": hash_json(prompt),
                    "input_digest": hash_json(inputs),
                    "schema_version": "1",
                    "latency_ms": (time.perf_counter() - start) * 1000,
                    "tokens_in": getattr(usage, "prompt_token_count", 0) or 0,
                    "tokens_out": getattr(usage, "candidates_token_count", 0) or 0,
                },
            }

            def finish(tx):
                cached = tx.get("model_cache/" + key)
                if cached.get("owner") != owner:
                    raise CallCapError("model_reservation_expired")
                tx.set("model_cache/" + key, {"status": "done", "result": result})
                tx.set(
                    "model_calls/" + owner,
                    {
                        "case_id": case_id,
                        "day": day,
                        "provider": provider,
                        "model": model,
                        "status": "done",
                        "usage": result["run"],
                    },
                )

            self.documents.transact(finish)
            return result
        except Exception:

            def fail(tx):
                cached = tx.get("model_cache/" + key)
                if cached and cached.get("owner") == owner:
                    tx.set("model_cache/" + key, {"status": "failed", "until": 0})
                tx.set(
                    "model_calls/" + owner,
                    {
                        "case_id": case_id,
                        "day": day,
                        "provider": provider,
                        "model": model,
                        "status": "failed",
                    },
                )

            self.documents.transact(fail)
            raise
