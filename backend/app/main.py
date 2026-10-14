from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, chat, documents, projects
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.database import models  # noqa: F401  (registers the tables for Alembic)
from app.services import file_storage

# NOTE: the tables are created with Alembic ("alembic upgrade head"), not with
# Base.metadata.create_all(). Mixing the two makes Alembic fail with "table already exists".


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    file_storage.ensure_dirs()  # data/uploads and data/temporary
    yield


app = FastAPI(title="Local Smart Notebook API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Total-Count"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# One prefix for everything: change API_PREFIX in .env (for example /api/v1).
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(projects.router, prefix=settings.api_prefix)
app.include_router(documents.router, prefix=settings.api_prefix)
# Task 4: persistent conversations and user messages (no AI response yet).
app.include_router(chat.router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


# Later tasks: query, summaries, analytics, ...


@app.get("/")
def read_root():
    return {"message": "Local Smart Notebook Backend is running successfully!"}
