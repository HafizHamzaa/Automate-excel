from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import phonenumbers
from sqlalchemy import select

from .config import settings
from .db import Assignment, Site, WageType, Worker, session_scope

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    "Name",
    "E-Commerce Number",
    "Phone Number",
    "Shift",
    "Site",
    "Designation",
    "Wage Type",
    "Daily Rate",
    "Base Salary",
    "OT Rate",
    "Weekend Rate",
]


def normalize_phone(raw: str | float | int | None, default_region: str = "SA") -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.startswith("+"):
            pn = phonenumbers.parse(s, None)
        else:
            pn = phonenumbers.parse(s, default_region)
        if not phonenumbers.is_valid_number(pn):
            return None
        return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return None


def _coerce_wage_type(v: str | None) -> WageType:
    s = (v or "").strip().lower()
    return WageType.daily if s in {"d", "daily", "day"} else WageType.salary


async def sync_once() -> None:
    xls_path = Path(settings.excel_file)
    if not xls_path.exists():
        logger.warning("Excel file not found at %s", xls_path)
        return

    # Read all sheets; owner may duplicate site sheets
    xl = pd.ExcelFile(str(xls_path))
    sheets = [s for s in xl.sheet_names if not s.lower().startswith("admin")]  # ignore admin sheets

    with session_scope() as s:
        for sheet_name in sheets:
            df = xl.parse(sheet_name)
            # Standardize columns
            df.columns = [c.strip() for c in df.columns]
            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                logger.warning("Sheet %s missing cols: %s", sheet_name, ", ".join(missing))
                continue

            # Ensure site record exists
            site_name = sheet_name.strip()
            site = s.scalar(select(Site).where(Site.name == site_name))
            if not site:
                site = Site(name=site_name, active=True)
                s.add(site)
                s.flush()

            for _, row in df.iterrows():
                phone = normalize_phone(row.get("Phone Number"))
                if not phone:
                    logger.warning("Skipping row with empty/invalid phone in sheet %s", sheet_name)
                    continue

                name = str(row.get("Name") or "").strip() or "Unnamed"
                ecommerce_number = str(row.get("E-Commerce Number") or "").strip() or None
                designation = str(row.get("Designation") or "").strip() or None
                shift = str(row.get("Shift") or "").strip() or None
                wage_type = _coerce_wage_type(str(row.get("Wage Type") or ""))
                daily_rate = float(row.get("Daily Rate") or 0) or None
                base_salary = float(row.get("Base Salary") or 0) or None
                ot_rate = float(row.get("OT Rate") or 0) or None
                weekend_rate = float(row.get("Weekend Rate") or 0) or None

                # Upsert worker
                worker = s.scalar(select(Worker).where(Worker.phone_e164 == phone))
                if worker:
                    worker.name = name
                    worker.ecommerce_number = ecommerce_number
                    worker.designation = designation
                    worker.wage_type = wage_type
                    worker.daily_rate = daily_rate
                    worker.base_salary = base_salary
                    worker.ot_rate_per_hour = ot_rate
                    worker.weekend_rate = weekend_rate
                else:
                    worker = Worker(
                        name=name,
                        ecommerce_number=ecommerce_number,
                        phone_e164=phone,
                        designation=designation,
                        wage_type=wage_type,
                        daily_rate=daily_rate,
                        base_salary=base_salary,
                        ot_rate_per_hour=ot_rate,
                        weekend_rate=weekend_rate,
                    )
                    s.add(worker)
                    s.flush()

                # Upsert assignment
                assignment = s.scalar(
                    select(Assignment).where(Assignment.worker_id == worker.id, Assignment.site_id == site.id)
                )
                if assignment:
                    assignment.shift = shift
                    assignment.active = True
                else:
                    assignment = Assignment(worker_id=worker.id, site_id=site.id, shift=shift, active=True)
                    s.add(assignment)

        logger.info("Excel sync complete from %s", xls_path)