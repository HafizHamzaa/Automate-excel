# Construction Worker Attendance & Payroll — One‑Click System (v1)

- One‑click start: `scripts/run.sh` (macOS/Linux) or `scripts/Run-Attendance.bat` (Windows)
- Configure `.env` from `.env.example`.
- Webhook runs inside the same process (FastAPI via uvicorn). Default timezone `Asia/Riyadh`.

## Quick start

1. Python 3.11+
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill values
4. `./scripts/run.sh` (or the `.bat` on Windows)

Folders created on first run: `data/`, `logs/`, `exports/daily/`, `exports/payroll/`.
