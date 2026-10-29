"""The client zone app (port 8000): the disputes console API, the Demo Bank app and the website."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from versoml import __version__
from versoml.config import ROOT
from versoml.contracts import Zone
from versoml.secrets import install_log_redaction
from versoml.shared import ratelimit
from versoml.shared.events import TICKER
from versoml.shared.policy import sessions
from versoml.shared.policy.sessions import OperatorSession
from versoml.zone_client.service import get_service

log = logging.getLogger("versoml.client.app")
DIST = ROOT / "frontend" / "dist"


class CreateCase(BaseModel):
    scenario_id: str | None = None
    complaint: dict | None = None


class Approve(BaseModel):
    """A person's answer. The signer comes from the operator session; an `approver` in the body is ignored."""

    action: str
    note: str | None = None
    tx_id: str | None = None
    reason_code: str | None = None
    approval_token: str | None = None


class Proposal(BaseModel):
    action: str
    note: str | None = None


class SealCheck(BaseModel):
    case_id: str
    root: str = ""


class IntakePreview(BaseModel):
    text: str
    customer_ref: str | None = None
    source: Literal["app", "email", "branch", "call_center", "web_form"] | None = None
    channel_hint: Literal["card", "transfer", "transfer_instant"] | None = None
    attachments: list[dict] | None = None
    received_at: str | None = None
    transaction_refs: list[str] | None = None


class KbAsk(BaseModel):
    question: str
    k: int = 6


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


# What reaches Bedrock from the website: a case run (directly, or from a Demo Bank dispute) and a knowledge answer.
LIMITED = [(re.compile(r"^/api/cases/[^/]+/run$"), "case_run"), (re.compile(r"^/api/bank/[^/]+/dispute$"), "case_run"),
           (re.compile(r"^/api/kb/ask$"), "kb_ask")]


@app.middleware("http")
async def public_limits(request: Request, call_next):
    """Per-person and shared limits on the calls that cost Bedrock time, so a public demo stays inside the quota."""
    if request.method == "POST":
        for pattern, policy in LIMITED:
            if pattern.match(request.url.path):
                refusal = ratelimit.check(policy, ratelimit.caller_of(request.headers))
                if refusal:
                    log.info("limit %s reached", refusal.policy)
                    return JSONResponse({"detail": refusal.text()}, status_code=429,
                                        headers={"Retry-After": str(refusal.retry_after)})
                break
    return await call_next(request)


def svc():
    return get_service()


def operator_session(request: Request) -> OperatorSession:
    """The signed-in person behind a call (Authorization: Bearer <session>), or 401."""
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else None
    try:
        return sessions.read(token)
    except sessions.SessionError as exc:
        raise HTTPException(401, str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc


Operator = Annotated[OperatorSession, Depends(operator_session)]


# ---------------------------------------------------------------- operator sessions


@app.post("/api/session/demo")
def demo_session() -> dict:
    """Demo mode: a named demo operator for this console. Every signature made with it says it was a demo one."""
    try:
        token, session = sessions.issue_demo()
    except sessions.SessionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"token": token, "operator": session.public()}


@app.get("/api/session")
def session_info(session: Operator) -> dict:
    return {"operator": session.public()}


# ---------------------------------------------------------------- meta and statistics


@app.get("/api/meta")
def meta() -> dict:
    s = svc()
    llm = s.rt.llm.describe()
    return {"zone": "client", "version": __version__, "llm": {k: llm[k] for k in ("mode", "region", "models", "live_ok", "fallback")},
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


# why an answer was refused -> its HTTP status; anything else (a stale or changed decision) is a conflict
REFUSED = {"missing": 404, "candidate": 400, "reason": 400, "action": 400, "role": 403, "policy": 403,
           "separation_of_duties": 403, "ledger": 503}


def _refused(result: dict) -> dict:
    if not result.get("ok"):
        raise HTTPException(REFUSED.get(str(result.get("code")), 409), result.get("detail") or "Refused.")
    return result


@app.post("/api/cases/{case_id}/approve")
async def approve(case_id: str, body: Approve, session: Operator) -> dict:
    if body.action not in ("approve", "reject", "pick_transaction"):
        raise HTTPException(400, "action must be approve, reject or pick_transaction")
    return _refused(await svc().approve(case_id, body.action, body.note, tx_id=body.tx_id, reason_code=body.reason_code,
                                        session=session, approval_token=body.approval_token))


@app.post("/api/cases/{case_id}/proposals")
def propose(case_id: str, body: Proposal) -> dict:
    """A suggested approve or reject from a client that cannot sign (the MCP tool): recorded, never applied."""
    return _refused(svc().propose(case_id, body.action, body.note))


@app.get("/api/cases/{case_id}/precedents")
def case_precedents(case_id: str, k: int = 3) -> list[dict]:
    found = svc().precedents(case_id, k=max(1, min(k, 10)))
    if found is None:
        raise HTTPException(404, "No such case")
    return found


# ---------------------------------------------------------------- free-form intake, customers, knowledge base


@app.post("/api/intake/preview")
def intake_preview(body: IntakePreview) -> dict:
    if not body.text.strip():
        raise HTTPException(400, "Send the complaint text.")
    return svc().intake_preview(body.model_dump())


@app.get("/api/customers")
def customers(q: str = "") -> list[dict]:
    return svc().customers(q, limit=20)


@app.get("/api/kb/search")
def kb_search(q: str = "", k: int = 6, kind: str | None = None) -> list[dict]:
    return svc().kb_search(q, k=max(1, min(k, 20)), kind=kind)


@app.post("/api/kb/ask")
async def kb_ask(body: KbAsk) -> dict:
    if not body.question.strip():
        raise HTTPException(400, "Send a question.")
    return await svc().kb_ask(body.question, k=max(1, min(body.k, 20)))


@app.get("/api/kb/stats")
def kb_stats() -> dict:
    return svc().kb_stats()


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


# The evidence file holds the transaction, the device session and the payee's IBAN: only an operator reads it, and
# reading it never seals. The public check behind the seal's QR code is /api/verify/seal.


@app.get("/api/ledger/{case_id}", dependencies=[Depends(operator_session)])
def ledger(case_id: str) -> dict:
    rt = svc().rt
    snapshot = rt.ledger.snapshot(case_id)
    snapshot["sealed"] = rt.ledger.summary(case_id)["sealed"]
    return snapshot


@app.get("/api/ledger/{case_id}/export", dependencies=[Depends(operator_session)])
def ledger_export(case_id: str) -> dict:
    from versoml.shared.ledger import LedgerError

    try:
        return svc().rt.ledger.export_dossier(case_id)
    except LedgerError as exc:
        raise HTTPException(409, "The case is not sealed yet, so there is no evidence file to export.") from exc


@app.post("/api/verify")
async def verify(request: Request) -> dict:
    """A whole evidence file (with `zone`) is checked as sent, by anyone. The console's short form
    {case_id, facts, seal} fills the rest from the ledger, so it needs an operator session."""
    from versoml.shared.ledger import LedgerError, verify_dossier

    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Send an evidence file (a JSON object).")
    rt = svc().rt
    if "zone" not in body and body.get("case_id"):
        operator_session(request)
        try:
            stored = rt.ledger.export_dossier(str(body["case_id"]))
        except LedgerError as exc:
            raise HTTPException(409, "The case is not sealed yet.") from exc
        body = {**stored, **{k: v for k, v in body.items() if v is not None}}
    return verify_dossier(body, public_key=rt.ledger.public_key())


@app.post("/api/verify/seal")
def verify_seal(body: SealCheck) -> dict:
    """The page the seal's QR code opens ({site}/verify/{case_id}#{root}) sends the case ID and the root from the
    code. The answer is whether the root matches a seal, the signature, the time and the counts; never the
    evidence. Without the right root it is the same 404 whether or not the case exists."""
    root = body.root.strip().lower()
    if not root:
        raise HTTPException(400, "Send the root from the QR code.")
    if not re.fullmatch(r"[0-9a-f]{64}", root):
        raise HTTPException(400, "The root from the QR code is 64 hexadecimal characters.")
    result = svc().rt.ledger.seal_check(body.case_id.strip(), root)
    if result is None:
        raise HTTPException(404, "No sealed evidence file matches this code.")
    return result


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
async def rules_params_set(request: Request, session: Operator) -> dict:
    """Needs the rules role. Who changed which parameter goes to the ledger, and that person does not sign the
    cases decided under their change."""
    try:
        return svc().set_rule_params(await request.json(), session)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/rules/changes", dependencies=[Depends(operator_session)])
def rules_changes() -> list[dict]:
    return svc().rule_changes()


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


@app.get("/mcp", include_in_schema=False)
def mcp_page(request: Request):
    """`/mcp` is also the console page that explains MCP: a browser gets the website, an MCP client goes to `/mcp/`.
    Declared before the mount, so it wins for the bare path only."""
    index = DIST / "index.html"
    if "text/html" in request.headers.get("accept", "") and index.exists():
        return FileResponse(index)
    return RedirectResponse("/mcp/", status_code=307)


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
    target = (DIST / path).resolve()
    # a decoded path can climb out of dist/ (../ or %2e%2e%2f): only serve files inside it
    if path and target.is_relative_to(DIST.resolve()) and target.is_file():
        return FileResponse(target)
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"zone": "client", "ui": "frontend/dist is missing: run `npm run build` in frontend/"})
