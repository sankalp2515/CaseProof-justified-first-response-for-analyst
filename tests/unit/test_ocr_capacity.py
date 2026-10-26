import asyncio
import threading
import time
from io import BytesIO
from types import SimpleNamespace

import httpx
from PIL import Image

from local_services import ocr


def burst(monkeypatch, count):
    active = peak = 0
    lock = threading.Lock()

    def recognize(data):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        return [{"text": "input", "box_2d": [0, 0, 10, 10]}]

    monkeypatch.setattr(ocr, "recognize", recognize)

    async def run():
        async with ocr.app.router.lifespan_context(ocr.app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=ocr.app), base_url="http://ocr"
            ) as client:
                return await asyncio.gather(
                    *[client.post("/v1/transcribe", content=b"pixels") for _ in range(count)]
                )

    return asyncio.run(run()), peak


def test_ocr_execution_is_bounded_without_rejecting_five_request_demo_burst(monkeypatch):
    responses, peak = burst(monkeypatch, 5)
    assert all(r.status_code == 200 for r in responses)
    assert peak <= 2


def test_ocr_admission_overload_is_explicit_and_releases_slots(monkeypatch):
    responses, peak = burst(monkeypatch, 9)
    assert sum(r.status_code == 429 for r in responses) == 1
    rejected = next(r for r in responses if r.status_code == 429)
    assert rejected.headers["Retry-After"] == "1"
    assert peak <= 2
    # A subsequent request is admitted: failures/completion cannot leak capacity.
    responses, _ = burst(monkeypatch, 1)
    assert responses[0].status_code == 200


def test_tesseract_cannot_oversubscribe_openmp_threads(monkeypatch):
    calls = []

    def subprocess_run(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stdout=b"level\ttext\tconf\n")

    monkeypatch.setattr(ocr.subprocess, "run", subprocess_run)
    image = BytesIO()
    Image.new("RGB", (20, 20), "white").save(image, format="PNG")
    assert ocr.recognize(image.getvalue()) == []
    assert calls[0]["env"]["OMP_THREAD_LIMIT"] == "1"
