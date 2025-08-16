from __future__ import annotations

import datetime as dt
import logging
import re
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .config import settings
from .db import Attendance, Site, Worker, session_scope

logger = logging.getLogger(__name__)

CODES: dict[str, tuple[bool, int]] = {
    "1": (True, 0),
    "2": (False, 0),
    "3": (True, 1),
    "4": (True, 2),
}


def _normalize_phone_incoming(msisdn: str) -> str:
    # WA sends numbers as digits without '+' for many regions; we accept with or without '+'
    msisdn = msisdn.strip()
    if msisdn.startswith("+"):
        return msisdn
    # Assume already E.164 without leading '+'
    return "+" + msisdn


async def parse_and_record(phone: str, text: str) -> None:
    tz = ZoneInfo(settings.timezone)
    today = dt.datetime.now(tz).date()

    t = (text or "").upper().replace(" ", "")
    present, ot = False, 0
    weekend = False

    if t in CODES:
        present, ot = CODES[t]
    else:
        m = re.match(r"P\+OT=(\d+)", t)
        if m:
            present, ot = True, int(m.group(1))
        elif t.startswith("P"):
            present, ot = True, 0
        elif t in {"OFF", "A"}:
            present, ot = False, 0
        if "WEEKEND" in t:
            weekend = True

    phone_norm = _normalize_phone_incoming(phone)

    with session_scope() as s:
        worker = s.scalar(select(Worker).where(Worker.phone_e164 == phone_norm))
        if not worker:
            logger.warning("Inbound from unknown phone %s", phone_norm)
            return
        # Resolve active assignment site (fallback: first assignment)
        assignment = None
        if worker.assignments:
            for a in worker.assignments:
                if a.active:
                    assignment = a
                    break
            assignment = assignment or worker.assignments[0]
        site_id = assignment.site_id if assignment else None
        if site_id is None:
            site = s.scalar(select(Site).where(Site.name == "Unassigned"))
            if not site:
                site = Site(name="Unassigned", active=True)
                s.add(site)
                s.flush()
            site_id = site.id

        # Upsert attendance for today
        att = s.scalar(
            select(Attendance).where(Attendance.worker_id == worker.id, Attendance.date == today)
        )
        code = 1 if present and ot == 0 else 2 if not present else 3 if ot == 1 else 4 if ot == 2 else 1
        if att:
            att.code = code
            att.ot_hours = ot
            att.weekend = weekend
            att.site_id = site_id
        else:
            att = Attendance(
                worker_id=worker.id,
                site_id=site_id,
                date=today,
                code=code,
                ot_hours=ot,
                weekend=weekend,
            )
            s.add(att)