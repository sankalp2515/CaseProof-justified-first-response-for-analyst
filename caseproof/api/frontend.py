"""Web routes for the local API service; the diagnostic Inspector stays available.

In the Compose stack the separate frontend service serves the React build and
proxies API paths here. `create_app` keeps a combined host for single-process
development and tests.
"""

import os
import time
from pathlib import Path

import httpx
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from caseproof.adapters.customer_links import CustomerLinks
from caseproof.cloud.body_limit import BodyLimit


def integrate_frontend(api, directory=None):
    if directory is not None:
        directory = Path(directory)
        if not (directory / "index.html").is_file():
            raise RuntimeError("Built frontend index.html is required")

    async def home(request):
        if directory is not None and (directory / "landing/index.html").is_file():
            return FileResponse(
                directory / "landing/index.html", headers={"Cache-Control": "no-cache"}
            )
        return RedirectResponse("/app/#/entry", status_code=303)

    async def customer(request):
        token = request.path_params["token"]
        try:
            CustomerLinks(api.state.orchestrator).resolve(token)
        except PermissionError:
            return JSONResponse({"detail": "customer_link_unavailable"}, status_code=403)
        return RedirectResponse("/app/#/victim/reply/" + token, status_code=303)

    async def readiness(request):
        settings = api.state.orchestrator.s
        healthy = True
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            for url in (
                settings.local_ocr_url,
                settings.trail_feed_url,
                settings.mock_services_url,
            ):
                try:
                    response = await client.get(url + "/health")
                    healthy = healthy and response.status_code == 200 and response.json().get("ok")
                except (httpx.HTTPError, ValueError):
                    healthy = False
        heartbeat = settings.data_dir / "worker.heartbeat"
        healthy = bool(
            healthy and heartbeat.exists() and time.time() - heartbeat.stat().st_mtime < 20
        )
        return JSONResponse(
            {"ok": healthy, "service": "caseproof", "synthetic": True},
            status_code=200 if healthy else 503,
        )

    # Insert only explicit web routes. Missing /v1 endpoints retain API 404s.
    routes = [
        Route("/", home),
        Route("/customer/{token}", customer),
        Route("/ready", readiness),
    ]
    if directory is not None:
        routes.append(Mount("/app", app=StaticFiles(directory=directory, html=True)))
    api.router.routes[0:0] = routes
    api.add_middleware(BodyLimit)

    @api.middleware("http")
    async def privacy_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith(("/v1/", "/customer/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    return api


def create_app():
    from caseproof.api.app import app

    return integrate_frontend(app, os.environ.get("FRONTEND_DIST", "/app/frontend/dist"))


def create_api():
    """API service only; static assets belong to the frontend service."""
    from caseproof.api.app import app

    return integrate_frontend(app)
