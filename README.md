# Local Smart Notebook

FastAPI + SQLite backend for authentication, notebooks, document uploads, and local AI presentation generation. Generate editable PowerPoint files from notebook documents and spreadsheet data.

See [Presentation generation](docs/presentations.md) for the current workflow, limitations, and potential future improvements.

## Setup (once)
    cd backend
    python -m venv .venv
    .venv\Scripts\Activate.ps1          # Windows PowerShell   (macOS/Linux: source .venv/bin/activate)
    pip install -r requirements.txt     # large: it includes the AI libraries
    cd ..
    copy .env.example .env              # macOS/Linux: cp   - then put a real SECRET_KEY in .env
    cd backend
    alembic upgrade head                # creates local_smart_notebook.db

## Run the API (from backend/)
    uvicorn app.main:app --reload       # http://127.0.0.1:8000/docs

## Run the tests (from the repository root)
    python -m pytest -q

Always start `uvicorn` and `alembic` from `backend/` (the database path is relative).
If you have an old `local_smart_notebook.db` that was created by `create_all`, delete it first.

## Endpoints (no prefix by default; set API_PREFIX=/api/v1 in .env to add one)
| | |
|---|---|
| Auth | `POST /auth/register` · `POST /auth/login` (form data: username = e-mail) · `GET /auth/me` |
| Notebooks ("projects" in the design) | `POST/GET /notebooks/` · `PUT/DELETE /notebooks/{notebook_id}` |
| Documents | `POST /documents` · `GET /documents` · `GET /documents/supported-types` · `GET/PATCH/DELETE /documents/{document_id}` · `GET /documents/{document_id}/download` |

Everything except register and login needs `Authorization: Bearer <token>`.
Users only see and change their own notebooks, documents, and presentations (other people's objects answer 404).

## Presentation endpoints

All paths use the same optional `API_PREFIX` as the other endpoints. All presentation routes require `Authorization: Bearer <token>` and enforce ownership where a notebook or presentation is addressed.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/presentations/options` | Available themes, directions, layouts, and slide limits. |
| POST | `/notebooks/{notebook_id}/presentations` | Start background generation; returns HTTP 202 and a presentation record. |
| GET | `/notebooks/{notebook_id}/presentations` | List presentations for a notebook. |
| GET | `/presentations/{presentation_id}` | Read status, current stage, warnings, and errors. |
| GET | `/presentations/{presentation_id}/deck` | Get the generated slide JSON. |
| PUT | `/presentations/{presentation_id}/deck` | Replace the complete deck JSON and render again without calling the LLM. |
| GET | `/presentations/{presentation_id}/download` | Download the completed editable `.pptx`. |
| DELETE | `/presentations/{presentation_id}` | Delete the presentation and its stored artifact; returns HTTP 204. |

Use the `id` returned by the create request to poll status until `COMPLETED` or `FAILED`. Review `warnings` even when generation completes: some slides may use fallback content. A completed file does not guarantee factual accuracy.

Before generating, apply the database migrations, ensure Ollama is running with `qwen2.5:7b-instruct` installed:

```powershell
ollama pull qwen2.5:7b-instruct
```

Avoid `--reload` while a presentation job is running. From `backend/`, use `uvicorn app.main:app` for uninterrupted testing.

See [Presentation generation](docs/presentations.md) for a request example, editing workflow, supported inputs, and future plans.

## Folders
See [Backend structure](docs/backend-structure.md).

Working on the presentation feature? See [Presentation architecture and developer guide](docs/presentation-architecture.md) (module map, how to add a layout, theme or chart type, how the tests are organised).

## Spreadsheet analysis in Docker

From the repository root, start Docker with Linux containers and build the worker image once (repeat after changing the worker or its dependencies).

```sh
docker build -t lsn-analysis:1 backend/app/analysis
```

Send a multipart request to the running backend. Prepend the configured API prefix if applicable.

```sh
curl -F "file=@tests/analysis/sales_test.csv" -F "question=What is the total per region?" http://localhost:8000/analysis/analyze
```

Analysis uses `qwen2.5-coder:7b`. Optional fields are `sheet` (Excel worksheet) and `show_prompt`. The response includes the generated code, model, input dimensions, `result_type`, and `result`. Tables use `columns`, `index`, and `data`; series use `name`, `index`, and `data`. A scalar is returned directly. Charts saved as `plot.png` are included as `plot_png_base64`.

The API host needs access to its local Docker engine. Each run gets a read-only input directory, a temporary writable filesystem, one CPU, 512 MiB of memory and a 30-second execution deadline. The container runs as an unprivileged user with networking disabled. Up to two sandboxes can run per API process. Invalid generated code or oversized output returns HTTP 422, sandbox unavailability returns 503, and a timeout returns 504.
