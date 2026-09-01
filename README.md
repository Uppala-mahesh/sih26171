# SIH PS171 Browser Agent (Milestone 1)

Milestone 1 prototype with FastAPI + Playwright backend and a minimal React dashboard.

## Backend

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

## Implemented endpoints

- `GET /health`
- `POST /api/browser/start`
- `POST /api/browser/stop`
- `GET /api/browser/screenshot`

## Notes

- Milestone 1 only: browser start/stop and screenshot loop from frontend to backend.
- AI components are intentionally deferred for next milestones.
