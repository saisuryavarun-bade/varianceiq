"""FastAPI application — serves the SPA and the SSE agent endpoint."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from app import __version__
from app.agent import VarianceAgent
from app.config import get_settings
from app.data_loader import DataStore, load_sample_store

settings = get_settings()
app = FastAPI(title="VarianceIQ", version=__version__)

# Single-process in-memory store. For multi-user, swap for a session-scoped cache.
_store: DataStore = load_sample_store()


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
    transactions_file: UploadFile = File(...),
) -> dict[str, Any]:
    """Replace the in-memory dataset with user-uploaded CSVs."""
    global _store

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        budget_path = tmp_path / "budget.csv"
        txn_path = tmp_path / "transactions.csv"

        with budget_path.open("wb") as fh:
            shutil.copyfileobj(budget_file.file, fh)
        with txn_path.open("wb") as fh:
            shutil.copyfileobj(transactions_file.file, fh)

        try:
            new_store = DataStore.from_csv(
                budget_path, txn_path, source=budget_file.filename or "upload"
            )
        except ValueError as exc:
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
