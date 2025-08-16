from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import and_, func, select

from .db import Attendance, PayrollLine, PayrollRun, Site, WageType, Worker, session_scope


def _month_range(year: int, month: int) -> tuple[dt.date, dt.date]:
    _, last = calendar.monthrange(year, month)
    return dt.date(year, month, 1), dt.date(year, month, last)


def run_month_end(year: int, month: int) -> Path:
    start, end = _month_range(year, month)
    month_id = f"{year}{month:02d}"

    out_dir = Path(f"/workspace/exports/payroll/{year}-{month:02d}")
    out_dir.mkdir(parents=True, exist_ok=True)
    all_lines: list[dict] = []

    with session_scope() as s:
        run = PayrollRun(month_yyyymm=month_id)
        s.add(run)
        s.flush()

        workers = s.scalars(select(Worker)).all()
        for w in workers:
            # Attendance aggregates
            q = select(
                func.sum(func.case((Attendance.code.in_([1, 3, 4]), 1), else_=0)),
                func.sum(Attendance.ot_hours),
                func.sum(func.case((Attendance.weekend == True, 1), else_=0)),  # noqa: E712
            ).where(
                and_(Attendance.worker_id == w.id, Attendance.date >= start, Attendance.date <= end)
            )
            days_worked, ot_hours, weekend_days = s.execute(q).one()
            days_worked = int(days_worked or 0)
            ot_hours = int(ot_hours or 0)
            weekend_days = int(weekend_days or 0)

            # Compute pay
            daily_rate = Decimal(str(w.daily_rate or 0))
            base_salary = Decimal(str(w.base_salary or 0))
            ot_rate = Decimal(str(w.ot_rate_per_hour or 0))
            weekend_rate = Decimal(str(w.weekend_rate or 0))

            if w.wage_type == WageType.daily:
                gross = daily_rate * days_worked + ot_rate * ot_hours + weekend_rate * weekend_days
            else:
                gross = base_salary + ot_rate * ot_hours + weekend_rate * weekend_days

            deductions = Decimal("0.00")
            net = gross - deductions

            # For simplicity, pick the first active site
            site_id = None
            if w.assignments:
                site_id = w.assignments[0].site_id

            line = PayrollLine(
                payroll_run_id=run.id,
                worker_id=w.id,
                site_id=site_id or 0,
                days_worked=days_worked,
                ot_hours=ot_hours,
                weekend_days=weekend_days,
                gross=float(gross),
                deductions=float(deductions),
                net=float(net),
            )
            s.add(line)

            all_lines.append(
                {
                    "Worker": w.name,
                    "Phone": w.phone_e164,
                    "Wage Type": w.wage_type.value,
                    "Days Worked": days_worked,
                    "OT Hours": ot_hours,
                    "Weekend Days": weekend_days,
                    "Gross": float(gross),
                    "Deductions": float(deductions),
                    "Net": float(net),
                }
            )

        # Export consolidated file
        df = pd.DataFrame(all_lines)
        out_path = out_dir / "all-sites-payroll.xlsx"
        with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Payroll")

        return out_path