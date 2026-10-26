"""Bounded, network-local Tesseract OCR. Input pixels are the only evidence source."""

import asyncio
import csv
import io
import os
import re
import subprocess
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from PIL import Image, ImageOps

from caseproof.domain.money_text import COMPLETE_MONEY, fragmented_money


@asynccontextmanager
async def lifespan(app):
    app.state.execution_slots = asyncio.Semaphore(2)
    app.state.admitted = 0
    yield


app = FastAPI(title="CaseProof local OCR", lifespan=lifespan)
Image.MAX_IMAGE_PIXELS = 20_000_000
DATE_PREFIX = re.compile(r"\b\d{4}-\d{2}-\d{2}")
ISO_MINUTE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\b")


@app.get("/health")
def health():
    result = subprocess.run(["tesseract", "--version"], capture_output=True, timeout=5)
    if result.returncode:
        raise HTTPException(503, "OCR engine unavailable")
    return {
        "ok": True,
        "provider": "tesseract",
        "version": result.stdout.decode().splitlines()[0],
        "max_executing": 2,
        "max_admitted": 8,
        "omp_thread_limit": 1,
    }


def recognize(data: bytes) -> list[dict]:
    """Run TSV OCR and reconstruct real line boxes in normalized image coordinates."""
    started = time.monotonic()
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError("pixel limit")
            image = ImageOps.autocontrast(ImageOps.grayscale(image))
            width, height = image.size
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
    except Exception:
        raise HTTPException(422, "invalid or oversized image") from None
    lines = recognize_lines(
        buffer.getvalue(), width, height, "6", 35 - (time.monotonic() - started)
    )
    # Re-read uncertain date-shaped lines from their own pixels. Never replace
    # characters from a bank record or infer a missing separator in Python.
    verified = 0
    retained = []
    for row in lines:
        prefix = DATE_PREFIX.search(row["text"])
        low = row.pop("_low_confidence", False)
        if prefix and (low or not ISO_MINUTE.search(row["text"])) and verified < 4:
            verified += 1
            replacement = reread_timestamp(image, row, started)
            if replacement:
                row = replacement
                low = False
        if not low:
            retained.append(row)
    lines = retained
    if any(fragmented_money(row["text"]) for row in lines):
        alternate = recognize_lines(
            buffer.getvalue(), width, height, "11", 35 - (time.monotonic() - started)
        )
        for i, row in enumerate(lines):
            if not fragmented_money(row["text"]):
                continue
            compact = re.sub(r"\s+", "", row["text"]).casefold()
            choices = [
                other
                for other in alternate
                if COMPLETE_MONEY.fullmatch(other["text"])
                and re.sub(r"\s+", "", other["text"]).casefold() == compact
                and boxes_overlap(row["box_2d"], other["box_2d"])
            ]
            if len(choices) == 1:
                lines[i] = choices[0]
    return sorted(lines, key=lambda line: (line["box_2d"][0], line["box_2d"][1]))


def boxes_overlap(first, second):
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(
        first[3], second[3]
    )


def reread_timestamp(image, row, started):
    width, height = image.size
    original = ISO_MINUTE.search(row["text"])
    if original:
        # The multilingual model can assign low confidence to a correctly read
        # Latin timestamp. Require a separate Latin-model pixel observation.
        data = io.BytesIO()
        image.save(data, format="PNG")
        alternate = recognize_lines(
            data.getvalue(),
            width,
            height,
            "6",
            35 - (time.monotonic() - started),
            language="eng",
        )
        choices = [
            candidate
            for candidate in alternate
            if original.group() in candidate["text"]
            and abs(candidate["box_2d"][0] - row["box_2d"][0]) <= 10
        ]
        if len(choices) == 1:
            if choices[0].pop("_low_confidence", False):
                choices[0]["uncertain_timestamp"] = True
            return choices[0]
        return None
    top, left, bottom, right = row["box_2d"]
    x = max(0, left * width // 1000 - 12)
    y = max(0, top * height // 1000 - 12)
    crop = image.crop(
        (x, y, min(width, right * width // 1000 + 12), min(height, bottom * height // 1000 + 12))
    )
    crop = crop.resize((crop.width * 2, crop.height * 2))
    data = io.BytesIO()
    crop.save(data, format="PNG")
    original_date = DATE_PREFIX.search(row["text"]).group()
    valid = []
    candidates = []
    for psm in ("13", "7"):
        candidates.extend(
            recognize_lines(
                data.getvalue(), crop.width, crop.height, psm, 35 - (time.monotonic() - started)
            )
        )
    for candidate in candidates:
        values = ISO_MINUTE.findall(candidate["text"])
        if len(values) != 1 or not values[0].startswith(original_date):
            continue
        try:
            datetime.fromisoformat(values[0])
        except ValueError:
            continue
        crop_top, crop_left, crop_bottom, crop_right = candidate["box_2d"]
        # Crop is scaled by two: map the actual second-pass box to the original.
        candidate["box_2d"] = [
            (y * 2000 + crop_top * crop.height) // (2 * height),
            (x * 2000 + crop_left * crop.width) // (2 * width),
            min(1000, (y * 2000 + crop_bottom * crop.height + 2 * height - 1) // (2 * height)),
            min(1000, (x * 2000 + crop_right * crop.width + 2 * width - 1) // (2 * width)),
        ]
        if candidate.pop("_low_confidence", False):
            candidate["uncertain_timestamp"] = True
        valid.append(candidate)
    values = {ISO_MINUTE.search(candidate["text"]).group() for candidate in valid}
    return valid[0] if len(values) == 1 else None


def recognize_lines(data, width, height, psm, timeout, language=None):
    if timeout <= 0:
        raise HTTPException(503, "OCR engine deadline exceeded")
    try:
        result = subprocess.run(
            [
                "tesseract",
                "stdin",
                "stdout",
                "-l",
                language or ("eng" if psm in {"7", "13"} else "eng+hin"),
                "--psm",
                psm,
                "tsv",
            ],
            input=data,
            capture_output=True,
            timeout=timeout,
            check=True,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
    except (subprocess.SubprocessError, OSError):
        raise HTTPException(503, "OCR engine failed") from None
    groups = defaultdict(list)
    for row in csv.DictReader(io.StringIO(result.stdout.decode("utf-8")), delimiter="\t"):
        if row["level"] == "5" and row["text"].strip() and float(row["conf"]) >= 0:
            groups[tuple(row[k] for k in ("page_num", "block_num", "par_num", "line_num"))].append(
                row
            )
    lines = []
    for words in groups.values():
        text = " ".join(w["text"] for w in words)
        low = any(float(w["conf"]) < 30 for w in words)
        date = DATE_PREFIX.search(text)
        if not date and psm != "13":
            words = [w for w in words if float(w["conf"]) >= 30]
            if not words:
                continue
            text = " ".join(w["text"] for w in words)
        left = min(int(w["left"]) for w in words)
        top = min(int(w["top"]) for w in words)
        right = max(int(w["left"]) + int(w["width"]) for w in words)
        bottom = max(int(w["top"]) + int(w["height"]) for w in words)
        lines.append(
            {
                "text": text,
                **({"_low_confidence": True} if low and date else {}),
                "box_2d": [
                    top * 1000 // height,
                    left * 1000 // width,
                    min(1000, (bottom * 1000 + height - 1) // height),
                    min(1000, (right * 1000 + width - 1) // width),
                ],
            }
        )
    return sorted(lines, key=lambda line: (line["box_2d"][0], line["box_2d"][1]))


@app.post("/v1/transcribe")
async def transcribe(request: Request):
    # Admission happens before reading a body. Waiting requests do not create
    # Tesseract processes or consume threadpool workers. One service process.
    if app.state.admitted >= 8:
        raise HTTPException(429, "OCR capacity exceeded", headers={"Retry-After": "1"})
    app.state.admitted += 1
    acquired = False
    try:
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 5 * 1024 * 1024:
                raise HTTPException(413, "image exceeds 5 MiB")
        try:
            await asyncio.wait_for(app.state.execution_slots.acquire(), timeout=5)
            acquired = True
        except TimeoutError:
            raise HTTPException(
                503, "OCR queue wait exceeded", headers={"Retry-After": "1"}
            ) from None
        from starlette.concurrency import run_in_threadpool

        return {
            "lines": await run_in_threadpool(recognize, bytes(data)),
            "provider": "tesseract",
            "model_id": "tesseract-eng-hin-bounded-v5",
        }
    finally:
        if acquired:
            app.state.execution_slots.release()
        app.state.admitted -= 1
