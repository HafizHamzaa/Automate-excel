from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

BASE = "https://graph.facebook.com/v20.0"


async def _post_with_retry(url: str, headers: dict[str, str], payload: dict[str, Any], max_retries: int = 3) -> dict[str, Any]:
    backoff_seconds = 1.5
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=20) as client:
        for attempt in range(1, max_retries + 1):
            try:
                r = await client.post(url, headers=headers, json=payload)
                if r.status_code in (429, 500, 502, 503, 504):
                    logger.warning("WA API %s: %s — attempt %d/%d", r.status_code, r.text, attempt, max_retries)
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds *= 2
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as exc:  # pragma: no cover
                last_exc = exc
                logger.exception("WA API error on attempt %d/%d", attempt, max_retries)
                await asyncio.sleep(backoff_seconds)
                backoff_seconds *= 2
        if last_exc:
            raise last_exc
        raise RuntimeError("WhatsApp API call failed without exception")


async def send_template(to_e164: str, name: str, params: list[str]) -> dict[str, Any]:
    url = f"{BASE}/{settings.phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.permanent_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164,
        "type": "template",
        "template": {
            "name": name,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in params],
                }
            ],
        },
    }
    return await _post_with_retry(url, headers, payload)


async def send_text(to_e164: str, text: str) -> dict[str, Any]:
    url = f"{BASE}/{settings.phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.permanent_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164,
        "type": "text",
        "text": {"body": text},
    }
    return await _post_with_retry(url, headers, payload)


async def send_attendance_prompt(name: str, to_e164: str, site: str, shift: str | None, date_str: str) -> None:
    params = [name, site, shift or "", date_str]
    try:
        await send_template(to_e164, "attendance_prompt_v1", params)
    except Exception:
        logger.exception("Failed to send attendance prompt to %s", to_e164)


async def send_owner_daily_summary(text: str) -> None:
    if not settings.owner_phone:
        logger.warning("OWNER_PHONE_E164 not set; skipping owner summary send")
        return
    try:
        await send_text(settings.owner_phone, text)
    except Exception:
        logger.exception("Failed to send owner summary")