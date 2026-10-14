from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Simple {"message": "..."} answer used by delete endpoints."""

    message: str
