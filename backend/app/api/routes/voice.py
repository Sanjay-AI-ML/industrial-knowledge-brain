"""POST /api/voice/query — multilingual voice interaction for field technicians.

Accepts an audio file upload (WAV, WebM, MP3, OGG, etc.), runs the full
voice pipeline (STT → translate → RAG → back-translate → optional TTS),
and returns a structured JSON response.

The endpoint is intentionally lenient about audio formats because field
technicians may be recording on various devices — faster-whisper and
ffmpeg handle the decoding.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.voice_pipeline import voice_pipeline
from app.models.schemas import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["voice"])

# Maximum audio file size (20 MB — generous for field recordings).
MAX_AUDIO_BYTES = 20 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Response schema
# --------------------------------------------------------------------------- #
class VoiceQueryResponse(BaseModel):
    """Structured response from the voice query endpoint."""

    transcript: str = Field("", description="Raw speech-to-text transcription.")
    detected_language: str = Field("en", description="ISO 639-1 language code detected by STT.")
    detected_language_name: str = Field("English", description="Human-readable language name.")
    query_english: str = Field("", description="English translation of the transcript (same as transcript if already English).")
    answer_english: str = Field("", description="RAG engine answer in English.")
    answer_translated: str = Field("", description="Answer translated back to the detected language.")
    audio_response_base64: str | None = Field(None, description="Base64-encoded WAV audio of the spoken answer (if TTS succeeded).")
    translation_method: str = Field("none", description="Which translation backend was used: 'bhashini', 'gemini', or 'none'.")
    confidence: str = Field("low", description="RAG confidence level: high / medium / low.")
    sources: list[dict] = Field(default_factory=list, description="Source citations from the RAG engine.")
    related_entities: list[dict] = Field(default_factory=list, description="Knowledge-graph entities related to the answer.")
    session_id: str = Field("", description="Conversation session ID for multi-turn follow-ups.")
    error: str | None = Field(None, description="Error message if any step in the pipeline failed.")


# --------------------------------------------------------------------------- #
# Health check
# --------------------------------------------------------------------------- #
@router.get("/voice/health")
async def voice_health() -> dict[str, object]:
    """Liveness probe for the voice subsystem."""
    from app.config import get_settings

    settings = get_settings()
    bhashini_configured = (
        settings.bhashini_api_key != "REPLACE_ME"
        and settings.bhashini_user_id != "REPLACE_ME"
    )
    return {
        "status": "ok",
        "whisper_model": settings.whisper_model_size,
        "whisper_device": settings.whisper_device,
        "bhashini_configured": bhashini_configured,
        "translation_fallback": "gemini" if not bhashini_configured else "bhashini",
    }


# --------------------------------------------------------------------------- #
# Main voice query endpoint
# --------------------------------------------------------------------------- #
@router.post(
    "/voice/query",
    response_model=VoiceQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit a voice query (audio upload) for multilingual RAG",
)
async def voice_query(
    audio: UploadFile = File(..., description="Audio file (WAV, WebM, MP3, OGG, etc.)"),
    role: str = Form("engineer", description="User role: technician, engineer, or auditor."),
    session_id: str = Form("", description="Optional session ID for multi-turn conversations."),
) -> VoiceQueryResponse:
    """Process a voice query through the multilingual pipeline.

    1. Transcribes the audio using faster-whisper (auto-detects language).
    2. Translates the transcript to English (if non-English) via Bhashini or Gemini.
    3. Queries the RAG engine with the English text.
    4. Translates the answer back to the original language.
    5. Optionally generates TTS audio of the translated answer.
    """
    # Validate role
    try:
        user_role = UserRole(role)
    except ValueError:
        user_role = UserRole.ENGINEER

    # Read and validate audio
    audio_bytes = await audio.read()
    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty audio file.",
        )
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file too large ({len(audio_bytes)} bytes). Max {MAX_AUDIO_BYTES} bytes.",
        )

    logger.info(
        "Voice query: file='%s', size=%d bytes, role=%s",
        audio.filename, len(audio_bytes), role,
    )

    # Run the pipeline (never raises — errors captured in result.error)
    sid = session_id if session_id else None
    result = voice_pipeline.process_audio(
        audio_bytes=audio_bytes,
        role=user_role,
        session_id=sid,
    )

    return VoiceQueryResponse(
        transcript=result.transcript,
        detected_language=result.detected_language,
        detected_language_name=result.detected_language_name,
        query_english=result.query_english,
        answer_english=result.answer_english,
        answer_translated=result.answer_translated,
        audio_response_base64=result.audio_response_base64,
        translation_method=result.translation_method,
        confidence=result.confidence,
        sources=result.sources,
        related_entities=result.related_entities,
        session_id=result.session_id,
        error=result.error,
    )
