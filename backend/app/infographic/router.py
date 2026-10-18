
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError

from app.infographic.schema import InfographicPlan
from app.infographic.pipeline import generate_infographic_plan

router = APIRouter(
    prefix="/api/infographic",
    tags=["Infographic"],
)


@router.post("/validate")
def validate_infographic(plan: InfographicPlan):
    """Validate the structure of a submitted infographic plan."""
    return {
        "success": True,
        "message": "Infographic schema validation passed.",
        "data": plan.model_dump(mode="json"),
    }


@router.post("/generate")
async def generate_infographic(file: UploadFile = File(...)):
    """
    Upload a text report, extract its infographic plan,
    validate the schema, and verify facts against the report.
    """
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

    try:
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

        # Runs extraction, schema validation, and data verification.
        plan = generate_infographic_plan(report)

        return {
            "success": True,
            "message": "Infographic generated and verified successfully.",
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
        # Includes schema/data verification errors raised by pipeline.py.
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Infographic validation failed.",
                "details": str(exc),
            },
        ) from exc

    except RuntimeError as exc:
        # For example, Ollama is unavailable or generation fails.
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Infographic generation failed.",
                "details": str(exc),
            },
        ) from exc

    finally:
        await file.close()
