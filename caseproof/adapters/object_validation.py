"""Shared evidence limits and content-addressed object identities."""

import re
from hashlib import sha256
from io import BytesIO

from PIL import Image


def validate_object_key(key):
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{64}", key):
        raise ValueError("invalid_object_key")
    if key[:2] != key[3:5]:
        raise ValueError("invalid_object_key")


def validate_evidence(data, mime_type):
    if not data or len(data) > 5 * 1024 * 1024:
        raise ValueError("file_limit")
    if mime_type == "text/plain":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("invalid_text") from None
        if b"\x00" in data:
            raise ValueError("invalid_text")
    elif mime_type in ("image/png", "image/jpeg"):
        signature = b"\x89PNG\r\n\x1a\n" if mime_type == "image/png" else b"\xff\xd8\xff"
        if not data.startswith(signature):
            raise ValueError("signature_mismatch")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 20_000_000 or max(image.size) > 10000:
                    raise ValueError("image_pixel_limit")
                image.verify()
        except Exception:
            raise ValueError("invalid_image") from None
    else:
        raise ValueError("unsupported_mime")
    digest = sha256(data).hexdigest()
    return digest[:2] + "/" + digest, digest
