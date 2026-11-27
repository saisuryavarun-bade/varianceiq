"""FastAPI application — serves the SPA and the SSE agent endpoint."""
from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from threading import BoundedSemaphore
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from openai import OpenAIError
from sse_starlette.sse import EventSourceResponse

from app import __version__
from app.agent import VarianceAgent
from app.config import get_settings
from app.data_loader import DataStore, load_sample_store
from app.review import build_review
from app.assist import investigate_finding, InvalidDraft

settings = get_settings()
app = FastAPI(title="VarianceIQ", version=__version__)

# Single-process in-memory store. For multi-user, swap for a session-scoped cache.
_store: DataStore = load_sample_store()
_ai_slots = BoundedSemaphore(1)


@app.middleware('http')
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/review')
def review(period: str | None = None, min_abs_variance: Decimal = Decimal('1000')):
    try:
        return build_review(_store, period, min_abs_variance)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class InvestigationRequest(BaseModel):
    review_id: str = Field(min_length=64, max_length=64)
    finding_id: str = Field(min_length=24, max_length=24)
    period: str | None = None
    min_abs_variance: Decimal = Field(default=Decimal('1000'), ge=0, allow_inf_nan=False)


@app.post('/api/review/investigate')
def investigate_selected(body: InvestigationRequest):
    # Capture one store reference: a concurrent upload cannot change this packet.
    store = _store
    try:
        report = build_review(store, body.period, body.min_abs_variance)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if report['review_id'] != body.review_id:
        raise HTTPException(409, 'The dataset or review policy changed. Refresh the review before investigating.')
    finding = next((f for f in report['findings'] if f['id'] == body.finding_id), None)
    if finding is None:
        raise HTTPException(404, 'Finding not present in this review.')
    if not settings.openai_api_key:
        raise HTTPException(503, 'AI is not configured. The complete deterministic review is still available.')
    if not _ai_slots.acquire(blocking=False):
        raise HTTPException(429, 'One AI investigation is already running. Try again when it finishes.')
    try:
        draft = investigate_finding(finding)
        return dict(review_id=report['review_id'], finding_id=finding['id'], draft=draft)
    except (OpenAIError, InvalidDraft):
        raise HTTPException(502, 'AI could not produce a usable draft. Your verified review is unchanged.')
    finally:
        _ai_slots.release()


# ---------------------------------------------------------------------------
# Static + index
# ---------------------------------------------------------------------------

if settings.static_dir.exists():
    app.mount(
        "/static",
        StaticFiles(directory=settings.static_dir),
        name="static",
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


# ---------------------------------------------------------------------------
# Dataset endpoints
# ---------------------------------------------------------------------------


@app.get("/api/dataset")
def dataset_summary() -> dict[str, Any]:
    """Return a summary of the currently-loaded dataset."""
    df = _store.budget_actuals
    periods = sorted(df["period"].unique().tolist())
    return {
        "source": _store.source,
        "row_count": int(len(df)),
        "transaction_count": int(len(_store.transactions)),
        "periods": periods,
        "departments": sorted(df["department"].unique().tolist()),
        "accounts": sorted(df["account"].unique().tolist()),
    }


@app.post("/api/upload")
async def upload(
    budget_file: UploadFile = File(...),
    transactions_file: UploadFile | None = File(None),
) -> dict[str, Any]:
    """Replace the in-memory dataset with user-uploaded CSVs."""
    global _store

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        budget_path = tmp_path / "budget.csv"
        txn_path = tmp_path / "transactions.csv"

        for uploaded, destination in ((budget_file, budget_path), (transactions_file, txn_path)):
            if uploaded is None:
                destination.write_text('date,period,department,account,vendor,amount,memo\n', encoding='utf-8')
                continue
            size = 0
            with destination.open('wb') as fh:
                while chunk := await uploaded.read(65536):
                    size += len(chunk)
                    if size > 5 * 1024 * 1024:
                        raise HTTPException(413, 'Each CSV must be 5 MB or smaller.')
                    fh.write(chunk)

        try:
            new_store = DataStore.from_csv(
                budget_path, txn_path, source=budget_file.filename or "upload"
            )
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    _store = new_store
    return {"status": "loaded", "rows": int(len(_store.budget_actuals))}


@app.post("/api/reset")
def reset_dataset() -> dict[str, Any]:
    """Restore the bundled sample dataset."""
    global _store
    _store = load_sample_store()
    return {"status": "reset"}


# ---------------------------------------------------------------------------
# Agent endpoint (SSE)
# ---------------------------------------------------------------------------


@app.get("/api/investigate")
async def investigate(period: str = "YTD", query: str | None = None):
    """Stream the agent's investigation as Server-Sent Events."""
    if not settings.enable_legacy_agent:
        raise HTTPException(410, 'Use the deterministic review and its optional finding-level AI action.')
    if not settings.openai_api_key:
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    "OPENAI_API_KEY is not configured on the server. "
                    "Set it in .env or as an environment variable."
                )
            },
        )

    agent = VarianceAgent(_store)

    async def event_generator():
        for event in agent.investigate(period=period, custom_query=query):
            yield {"event": event["type"], "data": json.dumps(event, default=str)}

    return EventSourceResponse(event_generator())


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "model": settings.openai_model,
        "key_configured": bool(settings.openai_api_key),
    }
