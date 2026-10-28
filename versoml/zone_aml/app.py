"""Aplicația zonei AML (port 8001): consola AML, intrarea diodei și MCP-ul zonei AML. Proces separat."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from versoml import __version__
from versoml.config import ROOT
from versoml.contracts import Zone
from versoml.secrets import install_log_redaction
from versoml.zone_aml.service import get_service

log = logging.getLogger("versoml.aml.app")
DIST = ROOT / "frontend" / "dist"


class Decide(BaseModel):
    action: str
    note: str | None = None
    analyst: str | None = None


class OsintQuery(BaseModel):
    target: str
    kind: str = "auto"


@asynccontextmanager
async def lifespan(app: FastAPI):
    install_log_redaction()
    await get_service().graph()
    async with AsyncExitStack() as stack:
        if MCP_APP is not None:  # managerul de sesiuni al MCP-ului prin HTTP
            await stack.enter_async_context(MCP_APP.router.lifespan_context(MCP_APP))
        yield
        await get_service().close()


app = FastAPI(title="VersoML · zona AML", version=__version__, lifespan=lifespan)
# Aplicația unică rulează pe portul zonei client; vederea AML citește direct din acest proces (datele nu trec
# prin zona client). Browserul analistului e singurul punct comun, la fel ca o consolă cu două ferestre.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                                                   "http://localhost:5174", "http://127.0.0.1:5174",
                                                   "http://localhost:8000", "http://127.0.0.1:8000"],
                   allow_methods=["*"], allow_headers=["*"])


def svc():
    return get_service()


@app.get("/api/meta")
def meta() -> dict:
    s = svc()
    llm = s.rt.llm.describe()
    return {"zone": "aml", "version": __version__, "llm": {k: llm[k] for k in ("mode", "region", "models", "live_ok")},
            "osint_mode": s.rt.settings.versoml_osint_mode, "urls": {"client": s.rt.client_url(), "aml": s.rt.aml_url()}}


@app.get("/api/aml/stats")
def stats() -> dict:
    return svc().stats()


@app.get("/api/aml/referrals")
def referrals() -> list[dict]:
    return svc().list_referrals()


@app.get("/api/aml/leads")
def leads() -> list[dict]:
    return svc().list_leads()


@app.get("/api/aml/leads/{lead_id}")
def lead(lead_id: str) -> dict:
    detail = svc().lead_detail(lead_id)
    if not detail:
        raise HTTPException(404, "Pistă inexistentă")
    return detail


@app.post("/api/aml/leads/{lead_id}/run")
async def run(lead_id: str) -> dict:
    if not svc().rt.leads.get(lead_id):
        raise HTTPException(404, "Pistă inexistentă")
    return {"run_id": await svc().run(lead_id)}


@app.get("/api/aml/leads/{lead_id}/events")
async def events(lead_id: str, request: Request):
    bus = svc().rt.bus

    async def stream():
        async for event in bus.subscribe(lead_id):
            if await request.is_disconnected():
                break
            yield {"event": "message", "id": str(event.seq), "data": event.model_dump_json()}

    return EventSourceResponse(stream(), ping=15)


@app.post("/api/aml/leads/{lead_id}/decide")
async def decide(lead_id: str, body: Decide) -> dict:
    if body.action not in ("file_rts", "close", "request_info", "hold_client"):
        raise HTTPException(400, "acțiune necunoscută")
    return await svc().decide(lead_id, body.action, body.note, body.analyst)


@app.post("/api/aml/osint")
async def osint(body: OsintQuery) -> dict:
    return await svc().osint_lookup(body.target, body.kind)


@app.get("/api/aml/kb/search")
def kb_search(q: str = "", k: int = 6) -> list[dict]:
    return svc().kb_search(q, k=max(1, min(k, 20)))


@app.get("/api/aml/campaigns")
def campaigns() -> list[dict]:
    return svc().campaigns()


@app.get("/api/aml/graph")
def network() -> dict:
    return svc().network()


@app.get("/api/aml/wall")
def wall() -> dict:
    from versoml.shared.policy import recent_decisions

    return {"decisions": [d.model_dump(mode="json") for d in recent_decisions(60)], "denials": svc().rt.denials[-40:]}


@app.get("/api/aml/ledger/{lead_id}")
def ledger(lead_id: str) -> dict:
    rt = svc().rt
    return {"facts": [f.model_dump(mode="json") for f in rt.ledger.facts(lead_id)], "verify": rt.ledger.verify(lead_id)}


# ---------------------------------------------------------------- dioda și fluxul core-banking


@app.post("/diode/inbox")
async def diode_inbox(request: Request) -> dict:
    raw = await request.body()
    signature = request.headers.get("X-VersoML-Signature", "")
    try:
        facts = svc().rt.diode.receive_facts(raw, signature)
    except Exception as exc:  # noqa: BLE001 - schemă strictă și semnătură: orice abatere e refuz
        raise HTTPException(400, f"DisputeFacts respins: {type(exc).__name__}") from exc
    return svc().receive(facts)


@app.post("/feed/core-tx")
async def core_feed(request: Request) -> dict:
    svc().ingest_core_tx(await request.json())
    return {"ok": True}


@app.post("/api/aml/reset")
def reset() -> dict:
    rt = svc().rt
    rt.leads.clear()
    rt.referrals.clear()
    return {"ok": True}


MCP_APP = None


def _mount_mcp() -> None:
    global MCP_APP
    try:
        from versoml.mcp_server.server import http_app

        MCP_APP = http_app(Zone.AML)
        app.mount("/mcp", MCP_APP)
    except Exception as exc:  # noqa: BLE001
        log.warning("MCP prin HTTP indisponibil: %s", exc)


_mount_mcp()

if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith(("api/", "diode/", "feed/", "mcp")):
        raise HTTPException(404)
    target = DIST / path
    if path and target.is_file():
        return FileResponse(target)
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"zone": "aml", "ui": "frontend/dist lipsește: rulează `npm run build` în frontend/"})
