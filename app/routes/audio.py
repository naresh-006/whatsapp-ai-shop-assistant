"""Audio API routes for voice transcription and voice order creation (Phase 15)."""

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel, Field

from app.models.order import Order
from app.services.audio_service import transcribe_audio_bytes, transcribe_base64_audio
from app.services.pipeline_service import process_natural_language_order

router = APIRouter(prefix="/audio", tags=["Audio & Voice"])


class Base64AudioRequest(BaseModel):
    audio_base64: str = Field(..., description="Base64 encoded audio string")
    filename: str = Field(default="voice_note.ogg")
    session_id: str = Field(default="voice_session")


class TranscriptionResponse(BaseModel):
    transcript: str


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio_file_endpoint(file: UploadFile = File(...)):
    """Transcribe an uploaded audio file (ogg, mp3, wav, m4a)."""
    try:
        contents = await file.read()
        transcript = transcribe_audio_bytes(contents, filename=file.filename or "audio.ogg")
        return TranscriptionResponse(transcript=transcript)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/transcribe-base64", response_model=TranscriptionResponse)
def transcribe_audio_base64_endpoint(payload: Base64AudioRequest):
    """Transcribe a base64 encoded audio payload."""
    try:
        transcript = transcribe_base64_audio(payload.audio_base64, filename=payload.filename)
        return TranscriptionResponse(transcript=transcript)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/order", response_model=Order)
async def voice_order_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form(default="voice_session"),
):
    """
    Phase 15: Voice-to-Bill Pipeline
    Accepts spoken voice note from Mother, transcribes speech, normalizes language,
    calculates exact prices, and returns draft bill.
    """
    try:
        contents = await file.read()
        transcript = transcribe_audio_bytes(contents, filename=file.filename or "voice_order.ogg")
        order = process_natural_language_order(transcript, session_id=session_id)
        return order
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
