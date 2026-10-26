"""Newly drawn fictional phone screens; real crops and optional photo effects."""

import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = next(
    (
        p
        for p in [
            Path("C:/Windows/Fonts/Nirmala.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
        ]
        if p.exists()
    ),
    Path("C:/Windows/Fonts/Nirmala.ttf"),
)


def render(
    path: Path,
    kind: str,
    lines: list[str],
    case_id: str,
    crop=False,
    effect=False,
    blur=False,
    template="personal",
) -> list[dict]:
    """Render per-line boxes; transformed mock boxes are explicitly approximate."""

    def font(size, devanagari=False):
        windows = Path("C:/Windows/Fonts/Nirmala.ttf")
        linux = Path("/usr/share/fonts/truetype/noto") / (
            "NotoSansDevanagari-Regular.ttf" if devanagari else "NotoSans-Regular.ttf"
        )
        selected = windows if windows.exists() else linux
        return (
            ImageFont.truetype(str(selected), size)
            if selected.exists()
            else ImageFont.load_default(size=size)
        )

    w, h = 720, 1280
    im = Image.new("RGB", (w, h), "#f2f5f8")
    d = ImageDraw.Draw(im)
    segments = []

    def line(text, x, y, size=27, color="#183d52"):
        if Path("C:/Windows/Fonts/Nirmala.ttf").exists():
            d.text((x, y), text, font=font(size), fill=color)
            segments.append({"text": text, "pixel_box": d.textbbox((x, y), text, font=font(size))})
            return
        cursor = x
        boxes = []
        for run in re.findall(r"[\u0900-\u097f]+|[^\u0900-\u097f]+", text):
            face = font(size, bool(re.match(r"[\u0900-\u097f]", run)))
            d.text((cursor, y), run, font=face, fill=color)
            boxes.append(d.textbbox((cursor, y), run, font=face))
            cursor += d.textlength(run, font=face)
        box = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        segments.append({"text": text, "pixel_box": box})

    line("11:29                  4G     93%", 30, 20, 20)
    d.rectangle((0, 66, w, 145), fill="#173e56")
    line(
        "Cedar Pay" if kind == "receipt" else "Messages" if kind == "messages" else "Recent calls",
        28,
        84,
        32,
        "white",
    )
    if kind == "receipt":
        d.ellipse((306, 174, 414, 282), fill="#137b58")
        line("OK", 332, 203, 31, "white")
        line("Payment successful", 200, 300, 32)
        y = 372
        for i, text in enumerate(lines):
            if i == 0:
                line(text, 54, y, 48)
                y += 105
            else:
                d.line((32, y - 12, 688, y - 12), fill="#dce3e9")
                for part in textwrap.wrap(text, 42):
                    line(part, 34, y, 25)
                    y += 40
                y += 25
    elif kind == "messages":
        line("Reported caller / unverified", 28, 168, 26)
        y = 230
        for i, text in enumerate(lines):
            chunks = textwrap.wrap(text, 37)
            height = 45 + 42 * len(chunks)
            x = 32 if i % 2 == 0 else 100
            d.rounded_rectangle(
                (x, y, 680, y + height), radius=20, fill="#dcece6" if i % 2 == 0 else "white"
            )
            for part in chunks:
                line(part, x + 15, y + 12, 25)
                y += 40
            line("11:" + str(2 + i).zfill(2), 580, y + 10, 18)
            y += 70
    else:
        y = 240
        for text in lines:
            line(text, 34, y, 30)
            y += 85
    line("Fictional demo " + case_id + " / " + template, 26, 1210, 18)
    if crop and kind == "receipt":
        utr = next((s["pixel_box"][1] for s in segments if s["text"].startswith("UTR:")), h)
        h = int(utr) - 14
        im = im.crop((0, 0, w, h))
        segments = [s for s in segments if s["pixel_box"][3] < h]
    if effect:
        im = im.transform(
            im.size,
            Image.Transform.QUAD,
            (7, 15, 0, h - 8, w - 3, h, w - 18, 0),
            resample=Image.Resampling.BICUBIC,
        ).rotate(1.2, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="#d4d8db")
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(15))
        segments = []
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, format="JPEG" if effect else "PNG", **({"quality": 62} if effect else {}))
    result = []
    for s in segments:
        x, y, X, Y = s["pixel_box"]
        result.append(
            {
                "text": s["text"],
                "box_2d": [
                    max(0, int(y / h * 1000)),
                    max(0, int(x / w * 1000)),
                    min(999, int(Y / h * 1000)),
                    min(999, int(X / w * 1000)),
                ],
            }
        )
    return result
