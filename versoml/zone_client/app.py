"""The client zone app (port 8000): the disputes console API, the Demo Bank app and the website."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from versoml import __version__
from versoml.config import ROOT
from versoml.contracts import Zone
from versoml.secrets import install_log_redaction
from versoml.shared.events import TICKER
from versoml.zone_client.service import get_service

log = logging.getLogger("versoml.client.app")
DIST = ROOT / "frontend" / "dist"


class CreateCase(BaseModel):
    scenario_id: str | None = None
    complaint: dict | None = None


class Approve(BaseModel):
    action: str
    note: str | None = None
    approver: str | None = None


class Counterfactual(BaseModel):
    field: str
    value: Any


class LetterCheck(BaseModel):
    body: str


class Attack(BaseModel):
    kind: str
    payload: str | None = None


class BankDispute(BaseModel):
    transaction_id: str
    text: str | None = None


class DemoScam(BaseModel):
    customer_ref: str = "CUST-DEMO-01"
    card_last4: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    install_log_redaction()
    service = get_service()
    await service.graph()

    async def outbox_loop():
        while True:
            await asyncio.sleep(20)
            try:
                await service.flush_outbox()
            except Exception:  # noqa: BLE001
                pass

    async with AsyncExitStack() as stack:
        if MCP_APP is not None:  # the session manager of MCP over HTTP
            await stack.enter_async_context(MCP_APP.router.lifespan_context(MCP_APP))
        task = asyncio.create_task(outbox_loop())
        yield
        task.cancel()
        await service.close()


app = FastAPI(title="VersoML · client zone", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
# The built UI is about 600 KB of JS and CSS; gzip cuts it to a third. SSE (text/event-stream) is never compressed.
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def cache_built_assets(request: Request, call_next):
    """Files under /assets/ carry a content hash in their name, so browsers can keep them for a year."""
    response = await call_next(request)
    if request.url.path.startswith("/assets/") and response.status_code == 200:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def svc():
    return get_service()


# ---------------------------------------------------------------- meta and statistics


@app.get("/api/meta")
def meta() -> dict:
    s = svc()
    llm = s.rt.llm.describe()
    return {"zone": "client", "version": __version__, "llm": {k: llm[k] for k in ("mode", "region", "models", "live_ok")},
            "osint_mode": s.rt.settings.versoml_osint_mode,
            "urls": {"client": s.rt.client_url(), "aml": s.rt.aml_url()}}


@app.get("/api/stats")
def stats() -> dict:
    return svc().stats()


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return svc().scenarios()


# ---------------------------------------------------------------- cases


@app.post("/api/cases")
async def create_case(body: CreateCase) -> dict:
    if not body.scenario_id and not body.complaint:
        raise HTTPException(400, "Send scenario_id or complaint.")
    try:
        case_id = svc().create_case(body.scenario_id, body.complaint)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown scenario: {exc}") from exc
    return {"case_id": case_id}


@app.get("/api/cases")
def list_cases() -> list[dict]:
    return svc().list_cases()


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str) -> dict:
    detail = svc().detail(case_id)
    if not detail:
        raise HTTPException(404, "No such case")
    return detail


@app.post("/api/cases/{case_id}/run")
async def run_case(case_id: str) -> dict:
    try:
        return {"run_id": await svc().run_case(case_id)}
    except KeyError as exc:
        raise HTTPException(404, "No such case") from exc


@app.get("/api/cases/{case_id}/events")
async def case_events(case_id: str, request: Request):
    bus = svc().rt.bus

    async def stream():
        async for event in bus.subscribe(case_id):
            if await request.is_disconnected():
                break
            yield {"event": "message", "id": str(event.seq), "data": event.model_dump_json()}

    return EventSourceResponse(stream(), ping=15)


@app.get("/api/ticker")
async def ticker(request: Request):
    bus = svc().rt.bus

    async def stream():
        for event in bus.ticker(30):
            yield {"event": "message", "data": event.model_dump_json()}
        async for event in bus.subscribe(TICKER, replay=False):
            if await request.is_disconnected():
                break
            yield {"event": "message", "data": event.model_dump_json()}

    return EventSourceResponse(stream(), ping=15)


@app.post("/api/cases/{case_id}/approve")
async def approve(case_id: str, body: Approve) -> dict:
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    return await svc().approve(case_id, body.action, body.note, body.approver)


@app.post("/api/cases/{case_id}/counterfactual")
def counterfactual(case_id: str, body: Counterfactual) -> dict:
    return svc().counterfactual(case_id, body.field, body.value)


@app.post("/api/cases/{case_id}/letter/check")
def letter_check(case_id: str, body: LetterCheck) -> dict:
    result = svc().letter_check(body.body)
    if not result.get("passed"):
        svc().rt.record_block(case_id, result.get("reasons", []), result.get("blocked_terms", []))
    return result


# ---------------------------------------------------------------- the evidence ledger


@app.get("/api/ledger/{case_id}")
def ledger(case_id: str) -> dict:
    rt = svc().rt
    snapshot = rt.ledger.snapshot(case_id)
    snapshot["sealed"] = rt.ledger.summary(case_id)["sealed"]
    return snapshot


@app.get("/api/ledger/{case_id}/export")
def ledger_export(case_id: str) -> dict:
    return svc().rt.ledger.export_dossier(case_id)


@app.post("/api/verify")
async def verify(request: Request) -> dict:
    from versoml.shared.ledger import verify_dossier

    body = await request.json()
    rt = svc().rt
    if "zone" not in body and body.get("case_id"):
        # the website sends {case_id, facts, seal} from /api/ledger; the rest of the file comes from the ledger
        body = {**rt.ledger.export_dossier(body["case_id"]), **{k: v for k, v in body.items() if v is not None}}
    return verify_dossier(body, public_key=rt.ledger.public_key())


# ---------------------------------------------------------------- rules


@app.get("/api/rules")
def rules() -> list[dict]:
    from versoml.shared.rules import catalog

    return catalog()


@app.get("/api/rules/params")
def rules_params() -> dict:
    from versoml.shared.rules import get_params

    return get_params()


@app.put("/api/rules/params")
async def rules_params_set(request: Request) -> dict:
    from versoml.shared.rules import set_params

    try:
        return set_params(await request.json())
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------- the wall


@app.get("/api/wall")
def wall() -> dict:
    return svc().wall_status()


@app.post("/api/wall/attack")
async def wall_attack(body: Attack) -> dict:
    return await svc().wall_attack(body.kind, body.payload)


@app.post("/diode/hold")
async def diode_hold(request: Request) -> dict:
    raw = await request.body()
    signature = request.headers.get("X-VersoML-Signature", "")
    try:
        signal = svc().rt.diode.receive_hold(raw, signature)
    except Exception as exc:  # noqa: BLE001 - anything off the schema or the signature is refused
        raise HTTPException(400, f"HoldSignal rejected: {type(exc).__name__}") from exc
    return svc().receive_hold(signal)


# ---------------------------------------------------------------- evaluation and MCP


@app.get("/api/eval")
def eval_report() -> dict:
    path = svc().rt.settings.var_dir / "eval" / "report.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "missing", "message": "No evaluation report yet. Run `versoml eval`."}


@app.get("/api/mcp")
def mcp_info() -> dict:
    from versoml.mcp_server.catalog import mcp_info as info

    return info(svc().rt.client_url())


# ---------------------------------------------------------------- Demo Bank


@app.get("/api/bank/{customer_ref}")
def bank(customer_ref: str) -> dict:
    return svc().bank_view(customer_ref)


@app.post("/api/bank/{customer_ref}/dispute")
async def bank_dispute(customer_ref: str, body: BankDispute) -> dict:
    return {"case_id": await svc().bank_dispute(customer_ref, body.transaction_id, body.text)}


@app.post("/api/demo/scam")
async def demo_scam(body: DemoScam) -> dict:
    # async: the payment also starts the feed to AML, as a task on the event loop
    return svc().demo_scam(body.customer_ref)


@app.post("/api/demo/reset")
def demo_reset() -> dict:
    """Clears the cases and notifications (for demo rehearsals)."""
    rt = svc().rt
    rt.cases.clear()
    rt.notifications.clear()
    return {"ok": True}


# ---------------------------------------------------------------- MCP over HTTP and the website


MCP_APP = None


def _mount_mcp() -> None:
    global MCP_APP
    try:
        from versoml.mcp_server.server import http_app

        MCP_APP = http_app(Zone.CLIENT)
        app.mount("/mcp", MCP_APP)
    except Exception as exc:  # noqa: BLE001 - the website and the API work without MCP over HTTP
        log.warning("MCP over HTTP unavailable: %s", exc)


_mount_mcp()

if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith(("api/", "diode/", "mcp")):
        raise HTTPException(404)
    target = DIST / path
    if path and target.is_file():
        return FileResponse(target)
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"zone": "client", "ui": "frontend/dist is missing: run `npm run build` in frontend/"})
