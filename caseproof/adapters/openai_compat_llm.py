import json
from types import SimpleNamespace

import httpx


class OpenAICompat:
    def __init__(self, settings):
        self.s = settings
        self.provider = settings.llm_provider
        self.url = (
            "https://api.groq.com/openai/v1"
            if self.provider == "groq"
            else "https://integrate.api.nvidia.com/v1"
        )
        self.key = (
            settings.groq_api_key if self.provider == "groq" else settings.nvidia_api_key
        ).get_secret_value()
        self.model_id = settings.groq_model if self.provider == "groq" else settings.nvidia_model
        if not self.model_id:
            r = httpx.get(
                self.url + "/models", headers={"Authorization": "Bearer " + self.key}, timeout=30
            )
            r.raise_for_status()
            self.model_id = sorted(x["id"] for x in r.json()["data"])[0]

    def generate(self, prompt, inputs, schema, image=None, mime_type=None):
        content = prompt + "\n" + json.dumps(inputs, ensure_ascii=False)
        if image:
            import base64

            content = [
                {"type": "text", "text": content},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:" + mime_type + ";base64," + base64.b64encode(image).decode()
                    },
                },
            ]
        r = httpx.post(
            self.url + "/chat/completions",
            headers={"Authorization": "Bearer " + self.key},
            json={
                "model": self.model_id,
                "messages": [{"role": "user", "content": content}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            timeout=45,
        )
        r.raise_for_status()
        body = r.json()
        u = body.get("usage", {})
        return json.loads(body["choices"][0]["message"]["content"]), SimpleNamespace(
            prompt_token_count=u.get("prompt_tokens", 0),
            candidates_token_count=u.get("completion_tokens", 0),
        )
