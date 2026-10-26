"""Bound total multipart traffic before FastAPI spools uploaded files."""


class BodyLimitExceeded(Exception):
    pass


class InvalidBodyLength(Exception):
    pass


class BodyLimit:
    def __init__(self, app, maximum=6 * 1024 * 1024):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        size, started = 0, False

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self.maximum:
                    raise BodyLimitExceeded()
            return message

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            seen_length = False
            for key, value in scope.get("headers", []):
                if key.lower() == b"content-length":
                    if seen_length or not value.isdigit() or len(value) > 20:
                        raise InvalidBodyLength()
                    seen_length = True
                    if int(value) > self.maximum:
                        raise BodyLimitExceeded()
            await self.app(scope, bounded_receive, tracked_send)
        except (BodyLimitExceeded, InvalidBodyLength) as error:
            if started:
                raise
            await send(
                {
                    "type": "http.response.start",
                    "status": 400 if isinstance(error, InvalidBodyLength) else 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            detail = (
                b"invalid_content_length"
                if isinstance(error, InvalidBodyLength)
                else b"request_body_limit"
            )
            await send({"type": "http.response.body", "body": b'{"detail":"' + detail + b'"}'})
