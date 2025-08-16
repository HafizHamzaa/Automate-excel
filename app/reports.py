from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import func, select

from .db import Attendance, Site, Worker, session_scope


def export_daily_summaries(run_date: dt.date | None = None) -> list[Path]:
    day = run_date or dt.date.today()
    out_paths: list[Path] = []
    with session_scope() as s:
        sites = s.scalars(select(Site).where(Site.active == True)).all()  # noqa: E712
        for site in sites:
            q = select(
                Worker.name,
                Attendance.code,
                Attendance.ot_hours,
            ).join(Attendance, Attendance.worker_id == Worker.id).where(
                Attendance.site_id == site.id, Attendance.date == day
            )
            rows = s.execute(q).all()
            df = pd.DataFrame(rows, columns=["Worker", "Code", "OT Hours"]).sort_values("Worker")
            present = int((df["Code"].isin([1, 3, 4])).sum()) if not df.empty else 0
            absent = int((df["Code"] == 2).sum()) if not df.empty else 0
            ot_hours = int(df["OT Hours"].sum()) if not df.empty else 0

            out_dir = Path("/workspace/exports/daily") / day.strftime("%Y-%m-%d")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"site-{site.name}-summary.xlsx"
            with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Attendance")
                meta = pd.DataFrame(
                    [[site.name, present, absent, ot_hours]],
                    columns=["Site", "Present", "Absent", "OT Hours"],
                )
                meta.to_excel(writer, index=False, sheet_name="Summary")
            out_paths.append(out_path)
    return out_paths


def summarize_site_day(site_id: int, day: dt.date) -> tuple[int, int, int]:
    with session_scope() as s:
        q = select(
            func.sum(func.case((Attendance.code.in_([1, 3, 4]), 1), else_=0)),
            func.sum(func.case((Attendance.code == 2, 1), else_=0)),
            func.sum(Attendance.ot_hours),
        ).where(Attendance.site_id == site_id, Attendance.date == day)
        present, absent, ot = s.execute(q).one()
        return int(present or 0), int(absent or 0), int(ot or 0)