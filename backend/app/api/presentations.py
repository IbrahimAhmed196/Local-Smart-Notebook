from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
 
from app.api.deps import get_current_user, get_owned_notebook, get_owned_presentation
from app.database.database import get_db
from app.database.models import Notebook, Presentation
from app.schemas.presentations import (
    PresentationCreate,
    PresentationOptionsOut,
    PresentationOut,
)
from app.schemas.slide_content import PresentationContent
from app.services import presentation_service as service
 
PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
 
# Every route needs a logged-in user. Ownership is checked by get_owned_notebook and
# get_owned_presentation (404 for other people's objects).
router = APIRouter(tags=["Presentations"], dependencies=[Depends(get_current_user)])
 
 
@router.get(
    "/presentations/options",
    response_model=PresentationOptionsOut,
    summary="Themes, layouts and limits (for the frontend form)",
)
def options():
    return PresentationOptionsOut.current()
 
 
@router.post(
    "/notebooks/{notebook_id}/presentations",
    response_model=PresentationOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start generating a presentation",
)
def create_presentation(
    data: PresentationCreate,
    notebook: Notebook = Depends(get_owned_notebook),
    db: Session = Depends(get_db),
):
    return service.create_presentation(db, notebook, data)
 
 
@router.get(
    "/notebooks/{notebook_id}/presentations",
    response_model=list[PresentationOut],
    summary="List the presentations of a notebook",
)
def list_presentations(
    notebook: Notebook = Depends(get_owned_notebook), db: Session = Depends(get_db)
):
    return service.list_presentations(db, notebook)
 
 
@router.get(
    "/presentations/{presentation_id}",
    response_model=PresentationOut,
    summary="Status of a presentation (poll this while it is generating)",
)
def get_presentation(presentation: Presentation = Depends(get_owned_presentation)):
    return presentation
 
 
@router.get(
    "/presentations/{presentation_id}/deck",
    response_model=PresentationContent,
    summary="The slide JSON of a presentation",
)
def get_deck(presentation: Presentation = Depends(get_owned_presentation)):
    return service.get_deck(presentation)
 
 
@router.put(
    "/presentations/{presentation_id}/deck",
    response_model=PresentationOut,
    summary="Replace the slide JSON and draw the file again (no AI call)",
)
def put_deck(
    deck: PresentationContent,
    presentation: Presentation = Depends(get_owned_presentation),
    db: Session = Depends(get_db),
):
    return service.update_deck(db, presentation, deck)
 
 
@router.get("/presentations/{presentation_id}/download", summary="Download the .pptx file")
def download(presentation: Presentation = Depends(get_owned_presentation)):
    path = service.get_download(presentation)
    return FileResponse(
        path, media_type=PPTX_TYPE, filename=f"{presentation.title[:80]}.pptx"
    )
 
 
@router.delete(
    "/presentations/{presentation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a presentation and its file",
)
def delete_presentation(
    presentation: Presentation = Depends(get_owned_presentation),
    db: Session = Depends(get_db),
):
    service.delete_presentation(db, presentation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
