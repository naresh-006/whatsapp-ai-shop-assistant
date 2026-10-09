"""Voice Input & Audio Transcription Service (Phase 15).

Converts spoken audio notes (from WhatsApp or mic) into text transcripts:
- Supports Whisper (OpenAI) and Gemini Audio (Google)
- Provides mock / fallback transcription for offline development & tests
"""

import io
import logging
import base64
from typing import BinaryIO
from app.config import settings

logger = logging.getLogger(__name__)


def _transcribe_free_speech_recognition(audio_bytes: bytes) -> str | None:
    """
    Free Speech-to-Text using speech_recognition + imageio_ffmpeg.
    Requires no API keys. Transcribes Indian English (en-IN) and Tamil (ta-IN).
    """
    try:
        import subprocess
        import imageio_ffmpeg
        import speech_recognition as sr

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", "pipe:0",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            "pipe:1",
        ]
        proc = subprocess.run(
            cmd,
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        wav_bytes = proc.stdout
        if not wav_bytes or len(wav_bytes) <= 44:
            return None

        r = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
            audio_data = r.record(source)

        # 1. Try Indian English
        try:
            text = r.recognize_google(audio_data, language="en-IN")
            if text and text.strip():
                logger.info("Free Google Speech Recognition (en-IN): '%s'", text)
                return text.strip()
        except sr.UnknownValueError:
            pass

        # 2. Try Tamil
        try:
            text = r.recognize_google(audio_data, language="ta-IN")
            if text and text.strip():
                logger.info("Free Google Speech Recognition (ta-IN): '%s'", text)
                return text.strip()
        except sr.UnknownValueError:
            pass

        return None
    except Exception as exc:
        logger.warning("Free Speech Recognition failed: %s", exc)
        return None


def transcribe_audio_bytes(
    audio_bytes: bytes,
    filename: str = "audio.ogg",
    language: str = "en",
) -> str:
    """
    Transcribes audio bytes into text.
    1. If test mock payload -> decodes mock text.
    2. If OpenAI API key is set -> uses OpenAI Whisper API.
    3. If Gemini API key is set -> uses Gemini audio understanding.
    4. Free engine -> Google Speech Recognition via speech_recognition + bundled ffmpeg.
    """
    if not audio_bytes:
        raise ValueError("Audio data cannot be empty.")

    # Option 1: Fast path for unit test mock audio payloads
    try:
        decoded_text = audio_bytes.decode("utf-8")
        if decoded_text.startswith("MOCK_AUDIO:"):
            return decoded_text.replace("MOCK_AUDIO:", "").strip()
    except Exception:
        pass

    # Option 2: OpenAI Whisper
    if settings.OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            transcript_obj = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                prompt="Tamil English Tanglish cigarette shop order: Filter, Kings, Scissor, Beedi, Bingo, Marie Light",
            )
            return transcript_obj.text.strip()
        except Exception as exc:
            logger.warning("OpenAI Whisper transcription failed: %s", exc)

    # Option 3: Gemini Audio
    if settings.GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            mime_type = "audio/ogg" if filename.endswith(".ogg") else "audio/wav"
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    "Transcribe this shop voice note exactly into text. Return ONLY the spoken words.",
                ],
            )
            if response.text:
                return response.text.strip()
        except Exception as exc:
            logger.warning("Gemini audio transcription failed: %s", exc)

    # Option 4: Free Google Speech Recognition (No API Key Required!)
    free_result = _transcribe_free_speech_recognition(audio_bytes)
    if free_result:
        return free_result

    raise ValueError(
        "Voice audio could not be recognized. Please speak clearly, "
        "add GEMINI_API_KEY into .env, or type your order directly as text."
    )


def transcribe_base64_audio(base64_data: str, filename: str = "audio.ogg") -> str:
    """Decode base64 string and transcribe."""
    # Strip data URL prefix if present (e.g. data:audio/ogg;base64,...)
    if "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]
    raw_bytes = base64.b64decode(base64_data)
    return transcribe_audio_bytes(raw_bytes, filename=filename)

