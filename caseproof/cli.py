import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import typer

from caseproof.config import Settings

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


@app.callback()
def main():
    pass


@app.command()
def smoke():
    from caseproof.adapters.gemini_llm import smoke_check

    typer.echo(smoke_check(Settings()))


@app.command("init-db")
def init_db():
    from caseproof.pipeline.orchestrator import Orchestrator

    Orchestrator(Settings())
    typer.echo("SQLite and object storage ready")


@app.command("load-bank")
def load_bank(count: int = 33):
    from kitgen.v3 import generate

    s = Settings()
    typer.echo(json.dumps(generate(s.eval_kit_v3, s.duckdb_path, count)))


@app.command("mock-server")
def mock_server(port: int = 8765):
    import uvicorn

    uvicorn.run("mock_services.bank_mock:app", host="127.0.0.1", port=port, access_log=False)


@app.command()
def serve(port: int = 8000):
    import uvicorn

    uvicorn.run("caseproof.api.app:app", host="127.0.0.1", port=port, access_log=False)


def ensure_mock_service(s):
    from urllib.parse import urlparse

    import httpx

    from caseproof.adapters.http_outbound import HTTPOutbound

    HTTPOutbound(s.mock_services_url, s.local_service_hosts)
    try:
        health = httpx.get(s.mock_services_url + "/health", timeout=2, trust_env=False).json()
        if health.get("synthetic") is not True:
            raise RuntimeError("port occupied by non-synthetic service")
        return
    except (httpx.ConnectError, httpx.ConnectTimeout):
        pass
    port = urlparse(s.mock_services_url).port or 8765
    s.data_dir.mkdir(parents=True, exist_ok=True)
    log = (s.data_dir / "mock-service.log").open("a")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    process = subprocess.Popen(
        [sys.executable, "-m", "caseproof.cli", "mock-server", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=log,
        stderr=log,
        creationflags=flags,
    )
    (s.data_dir / "mock_service.pid").write_text(str(process.pid))
    log.close()
    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError("mock service failed to start")
        try:
            r = httpx.get(s.mock_services_url + "/health", timeout=1, trust_env=False)
            if r.status_code == 200:
                return
        except (httpx.ConnectError, httpx.ConnectTimeout):
            pass
        time.sleep(0.2)
    raise RuntimeError("mock service start timed out")


@app.command()
def demo(
    case_id: str = typer.Argument("GOLD-001"),
    mode: str | None = typer.Option(None, "--mode"),
    allow_fallback: bool = False,
):
    from caseproof.adapters.demo_identity import DemoIdentity
    from caseproof.adapters.http_outbound import export
    from caseproof.domain.evidence import diff
    from caseproof.domain.review import approve
    from caseproof.pipeline.load import load_case
    from caseproof.pipeline.orchestrator import Orchestrator
    from mock_services.customer import reply

    s = Settings()
    if mode:
        s.llm_mode = mode
    s.allow_fallback = allow_fallback
    if not (s.eval_kit_v3 / "inputs" / (case_id + ".json")).exists():
        from kitgen.v3 import generate

        generate(s.eval_kit_v3, s.duckdb_path, 33)
    ensure_mock_service(s)
    o = Orchestrator(s)
    cid = case_id + "-demo-" + uuid.uuid4().hex[:6]
    load_case(o, s.eval_kit_v3, case_id, new_id=cid)
    from caseproof.domain.ledger import dt

    o.clock_as_of = dt(o.store.metadata(cid)["reported_at"])
    initial = o.process(cid)
    typer.echo(
        json.dumps(
            {
                "step": "investigate",
                "case_id": cid,
                "revision": initial.revision,
                "ledger_ids": [m.txn_id for m in initial.ledger_matches],
                "unreported": [u.model_dump() for u in initial.unreported],
                "linked": len(initial.linked),
                "readiness": initial.readiness.disposition,
                "requests": [
                    {"id": r.catalogue_id, "state": r.state, "score": r.score}
                    for r in initial.requests
                ],
            }
        )
    )
    requests = [r for r in initial.requests if r.state == "proposed"]
    after = reply(o, s.eval_kit_v3, cid, requests[0].request_id) if requests else initial
    if after.readiness.disposition == "REVIEW_REQUIRED":
        typer.echo(
            json.dumps(
                {
                    "case_id": cid,
                    "revision": after.revision,
                    "status": "human_review_required",
                    "readiness": after.readiness.model_dump(),
                    "inspector": "http://127.0.0.1:8000/inspector#case=" + cid,
                    "sent": False,
                },
                indent=2,
            )
        )
        return
    d = diff(initial, after)
    disposition = (
        "COMPLETE_HANDOFF"
        if after.readiness.disposition == "COMPLETE_CANDIDATE"
        else "ESCALATE_WITH_GAPS"
    )
    # The CLI is a scripted demo: the approval is explicitly simulated, never represented as
    # real human review.
    approve(
        o.store,
        cid,
        DemoIdentity().actor("reviewer"),
        after.revision,
        after.digest,
        disposition,
        "SIMULATED reviewer decision in authorised GOLD demo",
    )
    result = export(o, cid)
    providers = sorted({r.provider for r in after.run_meta})
    output = {
        "case_id": cid,
        "clock": after.clock.model_dump(),
        "trail": after.trail.get("summary"),
        "packet_id": result["packet"]["packet_id"],
        "outbound_message_ids": [r["message_id"] for r in result["outbound"]],
        "revision": after.revision,
        "readiness": after.readiness.disposition,
        "linked": len(after.linked),
        "new_claim_count": len(d["added"]),
        "synthetic": True,
        "approval": "simulated",
        "providers": providers,
        "models": sorted({r.model_id for r in after.run_meta}),
        "mode": "mock_or_mixed"
        if any(r.mode == "mock" for r in after.run_meta)
        else "live_or_cache",
        "inspector": "http://127.0.0.1:8000/inspector",
    }
    (s.data_dir / "last_demo.json").write_text(json.dumps(output, indent=2))
    (s.data_dir / ("last_demo_" + s.llm_mode + ".json")).write_text(json.dumps(output, indent=2))
    typer.echo(json.dumps(output, indent=2))


@app.command()
def worker(once: bool = False):
    from caseproof.pipeline.orchestrator import Orchestrator
    from caseproof.worker import run_one

    o = Orchestrator(Settings())
    while True:
        run_one(o.jobs, o)
        if once:
            break
        time.sleep(0.5)


@app.command("eval")
def evaluate(
    arm: str = typer.Option("C"),
    split: str = typer.Option("heldout"),
    kit: str = typer.Option("v3"),
    mode: str | None = typer.Option(None),
    limit: int | None = None,
):
    from eval.run import run

    s = Settings()
    if mode:
        s.llm_mode = mode
    if kit == "v3":
        from eval.v3 import run as run_v3

        typer.echo(json.dumps(run_v3(s, arm, split, limit), indent=2))
    else:
        typer.echo(json.dumps(run(s, arm, split, kit, limit), indent=2))


@app.command("export-bank")
def export_bank(directory: str = "var/bigquery"):
    from caseproof.adapters.duckdb_bank import DuckDBBank

    DuckDBBank(Settings().duckdb_path).export_csv(directory)
    typer.echo("Synthetic tables exported to " + directory)


@app.command()
def reset(confirm: bool = False):
    if not confirm:
        typer.echo(
            "Use reset --confirm to clear runtime case state. Evidence objects are retained."
        )
        return
    from sqlalchemy import text

    from caseproof.adapters.sqlite_casestore import CaseStore

    s = Settings()
    store = CaseStore(s.sqlite_url)
    with store.engine.begin() as db:
        for table in ("outbox", "approvals", "audit_events", "jobs", "snapshots", "cases"):
            db.execute(text("DELETE FROM " + table))
    typer.echo("Runtime case state cleared; objects and LLM cache retained")


if __name__ == "__main__":
    try:
        app()
    except Exception as e:
        typer.echo(
            json.dumps(
                {
                    "error_type": type(e).__name__,
                    ("manual_path"): (
                        "Inspect the case, job status, and docs/PROGRESS.md; no app"
                        "roval is bypassed."
                    ),
                }
            ),
            err=True,
        )
        raise SystemExit(1) from None
