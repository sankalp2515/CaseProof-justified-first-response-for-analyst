import json
import sqlite3
import time
from datetime import datetime, timezone

from caseproof.domain.contracts import hash_json


class CallCapError(RuntimeError):
    pass


class CacheMiss(RuntimeError):
    pass


class LLMCache:
    def __init__(self, s):
        self.s = s
        s.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = s.data_dir / "llm.sqlite"
        with self.connect() as db:
            db.executescript(
                (
                    "CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,resp"
                    "onse TEXT); CREATE TABLE IF NOT EXISTS calls(id INTEGER PR"
                    "IMARY KEY,case_id TEXT,day TEXT,provider TEXT,model TEXT,s"
                    "tatus TEXT);"
                )
            )

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def peek(self, provider, model, prompt, inputs):
        key = hash_json(
            {
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "inputs": inputs,
                "schema": "v1",
            }
        )
        with self.connect() as db:
            hit = db.execute("SELECT response FROM cache WHERE key=?", (key,)).fetchone()
        if hit:
            result = json.loads(hit[0])
            result["run"]["mode"] = "cache"
            return result
        return None

    def call(self, case_id, provider, model, prompt, inputs, fn):
        key = hash_json(
            {
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "inputs": inputs,
                "schema": "v1",
            }
        )
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            hit = db.execute("SELECT response FROM cache WHERE key=?", (key,)).fetchone()
            if hit:
                result = json.loads(hit[0])
                result["run"]["mode"] = "cache"
                return result
            if self.s.llm_mode == "cache_only":
                raise CacheMiss("response not cached")
            day = datetime.now(timezone.utc).date().isoformat()
            n = db.execute("SELECT count(*) FROM calls WHERE case_id=?", (case_id,)).fetchone()[0]
            daily = db.execute("SELECT count(*) FROM calls WHERE day=?", (day,)).fetchone()[0]
            if n >= min(24, self.s.llm_max_calls_per_case) or daily >= min(
                5000, self.s.llm_daily_call_cap
            ):
                raise CallCapError("LLM call cap reached")
            callid = db.execute(
                "INSERT INTO calls(case_id,day,provider,model,status) VALUES(?,?,?,?,?)",
                (case_id, day, provider, model, "reserved"),
            ).lastrowid
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
                    "schema_version": "1",
                    "input_digest": hash_json(inputs),
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                    "tokens_in": getattr(usage, "prompt_token_count", 0) or 0,
                    "tokens_out": getattr(usage, "candidates_token_count", 0) or 0,
                },
            }
            with self.connect() as db:
                db.execute("INSERT OR IGNORE INTO cache VALUES(?,?)", (key, json.dumps(result)))
                db.execute("UPDATE calls SET status='done' WHERE id=?", (callid,))
            return result
        except Exception:
            with self.connect() as db:
                db.execute("UPDATE calls SET status='failed' WHERE id=?", (callid,))
            raise
