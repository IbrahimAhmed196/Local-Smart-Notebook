# Backend structure

The backend follows the project's design diagram. Every folder and file of the design exists;
the ones marked *placeholder* contain only a docstring (and, for routers, an empty `APIRouter`)
until their task is implemented.

## Where the Stage 1 code lives
| Task | Files |
|---|---|
| 1. Database and notebooks | `database/{database,models}.py`, `database/repositories/project_repo.py`, `services/project_service.py`, `api/projects.py`, `schemas/projects.py`, `backend/alembic/` |
| 2. Authentication | `core/{config,security}.py`, `api/{auth,deps}.py`, `services/auth_service.py`, `database/repositories/user_repo.py`, `schemas/auth.py` |
| 3. Documents | `api/documents.py`, `services/{document_service,file_validation,file_storage}.py`, `database/repositories/document_repo.py`, `schemas/documents.py`, `ingestion/pipeline.py` (hook), `core/exceptions.py` |
| 4. Chat and integration (todo) | `api/chat.py`, `schemas/chat.py`, `services/chat_service.py` (placeholders), `main.py` |

## Files that are not in the design diagram (added on purpose)
| File | Why |
|---|---|
| `api/auth.py`, `schemas/auth.py`, `services/auth_service.py`, `database/repositories/user_repo.py` | login is a Stage 1 requirement; the diagram has no auth files |
| `api/deps.py` | `get_current_user` and the `get_owned_*` ownership checks used by every protected route |
| `schemas/projects.py`, `database/repositories/project_repo.py` | the diagram has `project_service.py` but no schema or repository for it |
| `core/exceptions.py` | domain errors (413, 415, 409 ...) turned into JSON by `main.py` |
| `services/file_storage.py`, `services/file_validation.py` | local file storage and upload checks; they live in `services/` because the diagram has no storage folder |

## Naming
The diagram says *project*, the team says *notebook*. The file names follow the diagram
(`projects.py`, `project_service.py`); the model is `Notebook` and the URLs are `/notebooks`.

## Where things went when the code was reorganised
| Before | Now |
|---|---|
| `api/notebooks.py` (queries inside the router) | `api/projects.py` + `services/project_service.py` + `database/repositories/project_repo.py` |
| `schemas/notebook_schema.py`, `auth_schema.py`, `document_schema.py` | `schemas/projects.py`, `auth.py`, `documents.py` |
| `core/file_security.py` | merged into `core/security.py` |
| `storage/file_storage.py` | `services/file_storage.py` |
| `services/ingestion_hook.py` | `ingestion/pipeline.py` |
| `backend/tests/`, `backend/.env.example`, `backend/pytest.ini` | `tests/`, `.env.example`, `pytest.ini` in the repository root |
| `app/database/main.py` (duplicate app) | removed |
