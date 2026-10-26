"""Structured request logs without evidence, cookies, capability tokens or raw paths."""

import json
import time
import uuid


def emit(event, severity="INFO", **values):
    print(json.dumps({"severity": severity, "event": event, **values}), flush=True)


def install(app):
    @app.middleware("http")
    async def request_log(request, call_next):
        start, request_id = time.perf_counter(), uuid.uuid4().hex
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        finally:
            route = request.scope.get("route")
            emit(
                "http_request",
                # 503 always means "retry shortly" here (bank publishing, virus scan
                # pending, task retry); only other 5xx are real failures.
                severity="ERROR"
                if status >= 500 and status != 503
                else ("WARNING" if status == 503 else "INFO"),
                request_id=request_id,
                route=getattr(route, "path", "unmatched"),
                method=request.method,
                status=status,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
            )
