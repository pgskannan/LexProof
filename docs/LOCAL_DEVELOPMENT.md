# Local Development

From `backend`, create and activate the Python 3.12 virtual environment,
install `requirements.txt`, configure the variables in
[CONFIGURATION.md](CONFIGURATION.md), then run:

```powershell
.venv\Scripts\python.exe -m uvicorn app.lexproof.main:app --host 127.0.0.1 --port 8000
```

From `frontend`, set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local`
and run `npm run dev`.

Validation commands:

```powershell
.venv\Scripts\python.exe -m compileall -q app scripts
.venv\Scripts\python.exe -m pytest tests/ -v
npm run typecheck
npm run build
```