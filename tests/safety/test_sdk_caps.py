from types import SimpleNamespace

from caseproof.adapters.gemini_llm import _smoke
from caseproof.config import Settings


def test_sdk_cannot_hide_additional_generation_calls(monkeypatch):
    def generate(**kwargs):
        config = kwargs["config"]
        assert config.automatic_continuation is False
        assert config.automatic_function_calling.disable is True
        return SimpleNamespace(text='{"ok":true}', usage_metadata=None)

    import caseproof.adapters.gemini_llm as module

    monkeypatch.setattr(
        module,
        "client",
        lambda s: SimpleNamespace(models=SimpleNamespace(generate_content=generate)),
    )
    assert _smoke(Settings(_env_file=None), "test")[0] == {"ok": True}
