# Local Smart Notebook: API test frontend (black & red)

Minimal React + Vite + Tailwind (v4) UI for exercising the FastAPI backend. Not a production app.

## Run
Backend (terminal 1, from the repo root):

    cd backend
    .venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
    alembic upgrade head
    uvicorn app.main:app --reload     # http://127.0.0.1:8000

Frontend (terminal 2):

    cd frontend
    npm install
    npm run dev                       # http://localhost:5173

Build check: `npm run build`

## Configuration
Default backend URL is `http://127.0.0.1:8000`. To change it (or if you set `API_PREFIX` in the backend `.env`),
copy `.env.example` to `.env.local` and edit `VITE_API_BASE_URL`.

## CORS
The backend allows `http://localhost:5173` and `http://localhost:3000`. Open the UI via `localhost`, or add your
origin to `cors_origins` in the backend settings.

## Endpoints used (all mounted in backend/app/main.py)
- `GET /` (health dot in the sidebar)
- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `POST/GET /notebooks/`, `PUT/DELETE /notebooks/{id}`
- `POST/GET /documents`, `GET /documents/supported-types`, `GET/PATCH/DELETE /documents/{id}`, `GET /documents/{id}/download`
- `POST/GET /conversations`, `GET/PATCH/DELETE /conversations/{id}`, `POST/GET /conversations/{id}/messages`

Files are stored by the backend (`data/uploads`); the frontend only sends them and reads the list back from the API.
The **API log** button (top right) shows every request with its status and timing.

Not connected because they do not exist yet in the backend: query/RAG, summaries, analytics, artifacts, jobs,
models, presentations, evaluation (their routers are empty and not mounted).
