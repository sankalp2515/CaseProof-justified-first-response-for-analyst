from types import SimpleNamespace

import pytest

from caseproof.adapters.llm_cache import CacheMiss, CallCapError, LLMCache
from caseproof.config import Settings


def test_per_case_cap_and_cached_calls_are_free(tmp_path):
    c = LLMCache(Settings(_env_file=None, data_dir=tmp_path, llm_mode="live"))

    def fn():
        return ({"ok": True}, SimpleNamespace())

    for i in range(8):
        c.call("C", "gemini", "m", "p", {"i": i}, fn)
    assert c.call("C", "gemini", "m", "p", {"i": 0}, fn)["run"]["mode"] == "cache"
    with pytest.raises(CallCapError):
        c.call("C", "gemini", "m", "p", {"i": 8}, fn)


def test_daily_cap_counts_failed_calls(tmp_path):
    c = LLMCache(Settings(_env_file=None, data_dir=tmp_path, llm_mode="live", llm_daily_call_cap=1))
    with pytest.raises(ValueError):
        c.call("C", "gemini", "m", "p", {}, lambda: (_ for _ in ()).throw(ValueError("failure")))
    with pytest.raises(CallCapError):
        c.call("D", "gemini", "m", "p", {}, lambda: ({}, None))


def test_cache_only_never_calls_provider(tmp_path):
    c = LLMCache(Settings(_env_file=None, data_dir=tmp_path, llm_mode="cache_only"))
    with pytest.raises(CacheMiss):
        c.call("C", "gemini", "m", "p", {}, lambda: pytest.fail("must not call"))
