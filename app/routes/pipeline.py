"""Pipeline API Router: End-to-end natural order processing & conversational corrections."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from app.models.order import Order
from app.services.pipeline_service import (
    process_natural_language_order,
    apply_conversational_correction,
)

router = APIRouter(prefix="/pipeline", tags=["End-to-End Pipeline"])


class ProcessVoiceOrderRequest(BaseModel):
    """Input payload with spoken transcript and conversational session ID."""
    transcript: str = Field(..., min_length=1, description="Voice transcript or typed order")
    session_id: str = Field(default="default_session", description="User session / WhatsApp phone number")


class ConversationalCorrectionRequest(BaseModel):
    """Input payload to adjust an existing active draft order."""
    session_id: str = Field(..., min_length=1, description="User session / WhatsApp phone number")
    correction: str = Field(..., min_length=1, description="Spoken or typed correction phrase")


@router.post("/process", response_model=Order)
def process_voice_order_endpoint(payload: ProcessVoiceOrderRequest):
    """
    Phase 9: Process voice/text order through the entire pipeline:
    Speech -> AI Extraction -> Product Resolver -> DB Lookup -> Deterministic Billing -> Draft Bill.
    """
    try:
        return process_natural_language_order(
            transcript=payload.transcript,
            session_id=payload.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/correct", response_model=Order)
def conversational_correction_endpoint(payload: ConversationalCorrectionRequest):
    """
    Phase 10: Apply natural language corrections to the active draft bill:
    - 'Change Filter to five'
    - 'Remove Kings'
    - 'Add two Marie Light ₹5'
    - 'Bingo ₹5' (clarification answer)
    """
    try:
        return apply_conversational_correction(
            session_id=payload.session_id,
            correction_text=payload.correction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
