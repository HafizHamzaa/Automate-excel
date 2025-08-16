from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request

from .attendance import parse_and_record
from .config import settings

logger = logging.getLogger(__name__)

app = FastAPI()


@app.get("/webhook")
async def verify(mode: str | None = None, challenge: str | None = None, token: str | None = None):
    if mode == "subscribe" and token == settings.verify_token:
        try:
            return int(challenge or 0)
        except Exception:
            return 0
    return {"status": "forbidden"}


@app.post("/webhook")
async def inbound(req: Request):
    data = await req.json()
    # Expected structure per WABA
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            msgs = value.get("messages") or []
            for m in msgs:
                frm = m.get("from")
                text = (m.get("text") or {}).get("body", "").strip()
                if frm and text:
                    await parse_and_record(frm, text)
    return {"status": "ok"}