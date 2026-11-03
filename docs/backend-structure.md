# Backend structure

The backend follows the project's design diagram. Every folder and file of the design exists;
the ones marked *placeholder* contain only a docstring (and, for routers, an empty `APIRouter`)
until their task is implemented. One exception: three placeholders that belonged to the presentation feature
(`agents/presentation_agent.py`, `api/jobs.py`, `llm/model_router.py`) were deleted in ARC-08 because nothing used them; the real
job code is `presentations/runner.py` and `jobs/manager.py`.

## Where the Stage 1 code lives
| Task | Files |
|---|---|
| 1. Database and notebooks | `database/{database,models}.py`, `database/repositories/project_repo.py`, `services/project_service.py`, `api/projects.py`, `schemas/projects.py`, `backend/alembic/` |
| 2. Authentication | `core/{config,security}.py`, `api/{auth,deps}.py`, `services/auth_service.py`, `database/repositories/user_repo.py`, `schemas/auth.py` |
| 3. Documents | `api/documents.py`, `services/{document_service,file_validation,file_storage}.py`, `database/repositories/document_repo.py`, `schemas/documents.py`, `ingestion/pipeline.py` (hook), `core/exceptions.py` |
| 4. Chat and integration (todo) | `api/chat.py`, `schemas/chat.py`, `services/chat_service.py` (placeholders), `main.py` |
| 5. Presentations | `api/presentations.py`, `services/presentation_service.py`, `schemas/presentations.py`, everything in `presentations/` (see `docs/presentation-architecture.md`), `llm/` (shared with chat), tests in `tests/presentations/` |

## Files that are not in the design diagram (added on purpose)
| File | Why |
|---|---|
| `api/auth.py`, `schemas/auth.py`, `services/auth_service.py`, `database/repositories/user_repo.py` | login is a Stage 1 requirement; the diagram has no auth files |
| `api/deps.py` | `get_current_user` and the `get_owned_*` ownership checks used by every protected route |
| `schemas/projects.py`, `database/repositories/project_repo.py` | the diagram has `project_service.py` but no schema or repository for it |
| `core/exceptions.py` | domain errors (413, 415, 409 ...) turned into JSON by `main.py` |
| `presentations/` | the whole generation pipeline of the presentation feature lives in one package: runner, generator, outline, slide writer, prompts, schemas, spreadsheet data (`data/`) and the PowerPoint renderer (`pptx/`). Only the API layer, the service and `main.py` import it |
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
| `agents/slide_content_agent.py`, `agents/citation_validator.py` (ARC-11) | `presentations/slide_content_agent.py`, `presentations/citation_validator.py` |
| `llm/prompts/outline.py`, `llm/prompts/slide_content.py` (ARC-11) | `presentations/prompts/outline.py`, `presentations/prompts/slide_content.py` |
| `schemas/slide_content.py`, `schemas/slides.py`, `schemas/layouts.py` (ARC-11) | `presentations/schemas/slide_content.py`, `slides.py`, `layouts.py` (`schemas/presentations.py`, the API schema, stays) |
| `services/presentation_context.py` (ARC-11) | `presentations/context/chunks.py` |
| `tools/pptx/` (ARC-11) | `presentations/pptx/` |
| `tools/pptx_charts.py`, `tools/pptx_themes.py` (ARC-10) | `presentations/pptx/charts.py`, `presentations/pptx/themes.py` |
| `tools/pptx_tool.py` (ARC-10, a shim that re-exported the renderer) | deleted: use `from app.presentations.pptx import build_pptx`; `_RENDERERS` is `presentations.pptx.registry._RENDERERS`, `_layout_of` is `presentations.pptx.planning._layout_of` |
| `tools/chart_tool.py` (ARC-09, 767 lines) | package `presentations/data/`: `limits`, `models`, `reader`, `cleaning`, `catalog`, `chart_builder`, `table_builder`, `facts` (`ChartToolError` is now `SlideDataError`) |
| `agents/presentation_agent.py`, `api/jobs.py`, `llm/model_router.py` (ARC-08) | deleted (empty placeholders) |
| `tests/test_presentation_*.py`, `test_presentations_api.py`, `test_chart_*.py`, `test_data_*.py`, `test_slide_*.py`, `test_citation_validator.py`, `test_layouts.py`, `test_pptx_tool.py`, `slide_samples.py` | `tests/presentations/` (shared LLM-client tests such as `test_ollama_client.py` stay in `tests/`) |
