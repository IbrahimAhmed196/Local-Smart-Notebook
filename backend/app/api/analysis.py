from pathlib import Path

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from fastapi.responses import JSONResponse

from app.analysis import codegen
from app.analysis.table import read_table
from app.sandbox import executor
from app.llm.errors import LlmUnavailableError
from app.llm.ollama_client import LlmChatError, OllamaChatClient, OllamaJSONClient

router = APIRouter(prefix="/analysis", tags=["analysis"])
MAX_CODE_RETRIES = 2
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _read_upload(file: UploadFile, sheet: str | None) -> pd.DataFrame:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".csv", ".txt", ".xlsx", ".xlsm", ".xls"}:
        raise HTTPException(400, f"Unsupported file type '{ext}'")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File larger than 50 MB")
    try:
        return read_table(file.file, ext, sheet)
    except Exception as exc:
        raise HTTPException(400, f"Could not read file: {exc}") from exc


@router.post("/schema")
def schema(file: UploadFile = File(...), sheet: str | None = Form(None)):
    df = _read_upload(file, sheet)
    return {"filename": file.filename, "schema": codegen.build_schema(df)}


@router.post("/analyze")
def analyze(
    file: UploadFile = File(...),
    question: str = Form(...),
    sheet: str | None = Form(None),
    show_prompt: bool = Form(False),
):
    """Generate pandas code and return it with the result from Docker."""
    if not question.strip():
        raise HTTPException(400, "question is empty")
    df = _read_upload(file, sheet)
    prompt = codegen.build_user_prompt(codegen.build_schema(df), question)
    client = OllamaChatClient(model_name="qwen2.5-coder:7b")
    ext = Path(file.filename).suffix.lower()
    generation_prompt = prompt
    for attempt in range(MAX_CODE_RETRIES + 1):
        try:
            code = codegen.generate_from_prompt(client, generation_prompt)
        except LlmChatError as exc:
            raise HTTPException(503, str(exc)) from exc

        error = codegen.check_syntax(code)
        if error is None:
            try:
                result = executor.execute(file.file, ext, sheet, code)
                break
            except executor.SandboxError as exc:
                if exc.status != 422:
                    return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": code})
                error = str(exc)

        if attempt == MAX_CODE_RETRIES:
            return JSONResponse(status_code=422, content={"detail": error, "code": code})
        generation_prompt = codegen.repair_prompt(prompt, code, error)

    response = {
        "model": client.model_name,
        "rows": len(df),
        "columns": list(map(str, df.columns)),
        "code": code,
        "syntax_error": None,
        **result,
    }
    if show_prompt:
        response["prompt"] = prompt
    return response
