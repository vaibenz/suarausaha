"""HTTP API for the web app. Run with: uvicorn suarausaha.api:app --reload"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .bookkeeper import make_bookkeeper
from .ledger import Ledger

MAX_AUDIO_BYTES = 10 * 1024 * 1024
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/aac"}


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def create_app(ledger: Ledger | None = None, bookkeeper=None) -> FastAPI:
    ledger = ledger or Ledger(os.environ.get("SUARAUSAHA_DB", "suarausaha.db"))
    bookkeeper = bookkeeper or make_bookkeeper(ledger)
    app = FastAPI(title="SuaraUsaha", version="0.1.0")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "engine": bookkeeper.engine, "audio": bookkeeper.engine == "gemini"}

    @app.post("/api/entries/text")
    def from_text(body: TextIn) -> dict:
        return bookkeeper.process_text(body.text).to_dict()

    @app.post("/api/entries/voice")
    async def from_voice(audio: UploadFile = File(...)) -> dict:
        mime = (audio.content_type or "").split(";")[0]
        if mime not in AUDIO_TYPES:
            raise HTTPException(415, f"Unsupported audio type {mime or 'unknown'}")
        data = await audio.read()
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Audio is larger than 10 MB")
        try:
            return bookkeeper.process_audio(data, mime).to_dict()
        except NotImplementedError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/entries")
    def entries(day: date | None = None) -> list[dict]:
        return [e.to_dict() for e in ledger.list(day)]

    @app.delete("/api/entries/last")
    def undo() -> dict:
        entry = ledger.undo_last()
        if entry is None:
            raise HTTPException(404, "No entries")
        return entry.to_dict()

    @app.get("/api/summary")
    def summary(day: date | None = None) -> dict:
        return ledger.summary(day)

    dist = Path(os.environ.get("SUARAUSAHA_WEB_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app() if os.environ.get("SUARAUSAHA_NO_AUTOAPP") != "1" else None
