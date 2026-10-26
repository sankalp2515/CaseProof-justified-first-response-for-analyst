import json
from pathlib import Path

from google import genai
from google.genai import types


def client(settings):
    if settings.llm_provider == "vertex":
        if not settings.google_cloud_project.strip() or not settings.google_cloud_location.strip():
            raise ValueError("Vertex requires GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION")
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            http_options=types.HttpOptions(
                api_version="v1",
                timeout=45000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=45000, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    )


def select_model(settings):
    if settings.gemini_model:
        return settings.gemini_model
    if settings.llm_provider == "vertex":
        raise ValueError("Vertex requires an explicitly configured GEMINI_MODEL")
    p = settings.data_dir / "model_choice.json"
    if p.exists():
        return json.loads(p.read_text())["model"]
    c = client(settings)
    names = [
        m.name.removeprefix("models/")
        for m in c.models.list()
        if "generateContent" in (m.supported_actions or [])
    ]
    choices = [
        n
        for n in names
        if "gemini" in n
        and "flash" in n
        and not any(x in n for x in ["image", "tts", "live", "preview", "experimental"])
    ]
    if not choices:
        raise RuntimeError("no fast Gemini model available")
    model = (
        "gemini-3.1-flash-lite"
        if "gemini-3.1-flash-lite" in choices
        else sorted(
            [n for n in choices if n.startswith("gemini-") and n[7:8].isdigit()], reverse=True
        )[0]
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model": model, "available_models": names}))
    with (Path(__file__).resolve().parents[2] / "docs/decisions.md").open("a") as f:
        f.write(
            "\n- No GEMINI_MODEL variable supplied. Selected "
            + model
            + " from accessible generateContent models; alternative: explicit configured model.\n"
        )
    return model


def smoke_check(settings):
    if settings.effective_mode == "mock":
        return json.dumps(
            {"mode": "mock", "notice": "No configured key or explicit mock mode; no live call."}
        )
    try:
        from caseproof.adapters.llm_cache import LLMCache

        model = select_model(settings)
        cache = LLMCache(settings)
        inputs = {"task": "return ok true"}
        if settings.llm_provider == "vertex":
            inputs.update(
                project=settings.google_cloud_project, location=settings.google_cloud_location
            )
        response = cache.call(
            "smoke",
            settings.llm_provider,
            model,
            "smoke-v1",
            inputs,
            lambda: _smoke(settings, model),
        )
        return json.dumps(
            {
                "mode": response["run"]["mode"],
                "provider": settings.llm_provider,
                "model": model,
                "response": response["data"],
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "mode": "failed",
                "error": "LLM_PROVIDER_ERROR",
                "notice": "Live smoke failed; no fallback was used",
                "error_type": type(e).__name__,
                "status_code": getattr(e, "code", None),
            }
        )


def _smoke(settings, model):
    c = client(settings)
    r = c.models.generate_content(
        model=model,
        contents="Return JSON {ok:true}.",
        config=types.GenerateContentConfig(
            automatic_continuation=False,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            response_mime_type="application/json",
            response_json_schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            },
        ),
    )
    return json.loads(r.text), r.usage_metadata
