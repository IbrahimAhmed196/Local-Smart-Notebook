
"""FastAPI endpoints for infographic validation, generation, and rendering."""

from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.infographic.pipeline import generate_infographic_plan
from app.infographic.rendering import (
    RenderingError,
    render_infographic,
)
from app.infographic.schema import InfographicPlan


router = APIRouter(
    prefix="/api/infographic",
    tags=["Infographic"],
)


@router.post("/validate")
def validate_infographic(plan: InfographicPlan):
    """Validate the submitted plan's schema and return normalized JSON."""
    return {
        "success": True,
        "message": "Infographic schema validation passed.",
        "data": plan.model_dump(mode="json"),
    }


async def _read_text_report(file: UploadFile) -> str:
    """Read a UTF-8 .txt upload and return its non-empty text."""
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No filename was provided.",
        )

    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=415,
            detail="Currently, only .txt reports are supported.",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    try:
        report = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="The report must be a valid UTF-8 text file.",
        ) from exc

    if not report.strip():
        raise HTTPException(
            status_code=400,
            detail="The report contains no readable text.",
        )

    return report


async def _render_response(
    plan: InfographicPlan,
    output_format: str,
    scale: float,
) -> Response:
    """Render a validated plan and return the artifact to the client."""
    result = await render_infographic(
        plan,
        output_format=output_format,
        scale=scale,
    )

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": (
                f'inline; filename="infographic.{result.extension}"'
            )
        },
    )


@router.post("/generate")
async def generate_infographic(file: UploadFile = File(...)):
    """Analyze a report and return a validated infographic plan."""
    try:
        report = await _read_text_report(file)
        plan = generate_infographic_plan(report)

        return {
            "success": True,
            "message": (
                "Infographic plan generated and verified successfully."
            ),
            "data": plan.model_dump(mode="json"),
        }

    except HTTPException:
        raise

    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Schema validation failed.",
                "details": exc.errors(include_url=False),
            },
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Infographic validation failed.",
                "details": str(exc),
            },
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Infographic generation failed.",
                "details": str(exc),
            },
        ) from exc

    finally:
        await file.close()


@router.post("/render")
async def render_existing_plan(
    plan: InfographicPlan,
    output_format: Literal["png", "html"] = Query(
        "png",
        alias="format",
    ),
    scale: float = Query(2.0, ge=1.0, le=3.0),
):
    """Render an existing validated infographic plan."""
    try:
        return await _render_response(
            plan,
            output_format,
            scale,
        )

    except HTTPException:
        raise

    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Schema validation failed.",
                "details": exc.errors(include_url=False),
            },
        ) from exc

    except RenderingError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Infographic rendering failed.",
                "details": str(exc),
            },
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Infographic rendering failed.",
                "details": str(exc),
            },
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid rendering request.",
                "details": str(exc),
            },
        ) from exc


@router.post("/generate-image")
async def generate_and_render_infographic(
    file: UploadFile = File(...),
    output_format: Literal["png", "html"] = Query(
        "png",
        alias="format",
    ),
    scale: float = Query(2.0, ge=1.0, le=3.0),
):
    """Upload report -> analyze -> validate -> render."""
    try:
        report = await _read_text_report(file)
        plan = generate_infographic_plan(report)

        return await _render_response(
            plan,
            output_format,
            scale,
        )

    except HTTPException:
        raise

    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Schema validation failed.",
                "details": exc.errors(include_url=False),
            },
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Infographic validation failed.",
                "details": str(exc),
            },
        ) from exc

    except RenderingError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Infographic generation or rendering failed.",
                "details": str(exc),
            },
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Infographic generation or rendering failed.",
                "details": str(exc),
            },
        ) from exc

    finally:
        await file.close()

