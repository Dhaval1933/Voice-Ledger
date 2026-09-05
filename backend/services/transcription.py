"""
ASR (Automatic Speech Recognition) service with provider abstraction.

Supports:
- MockASRProvider: deterministic Hinglish transcripts for demo/testing
- OpenAIWhisperProvider: OpenAI Whisper API
- GroqWhisperProvider: Groq Whisper-compatible API

The mock provider allows the full pipeline to work without any API keys.
"""

import random
from abc import ABC, abstractmethod
from typing import Optional

from backend.config import Settings


# ── Mock Transcription Pool ───────────────────────────────────────────────────

MOCK_TRANSCRIPTS = [
    "Sharma ji ne 450 ka rashan liya, 200 cash diya baaki kal denge.",
    "Ramesh bhai ne 1200 ka saman liya, pura UPI kar diya.",
    "Sita ji ka purana udhar 800 tha, 500 cash de diya.",
    "Mohan ne 600 ka kirana liya, pura udhar likh do.",
    "Gupta ji ne 950 ka maal liya, 450 cash aur 500 UPI kiya.",
    "Verma ji ne 300 ka tel aur 200 ka aata liya, pura cash diya.",
    "Rani didi ne 1500 ka saman liya, 1000 UPI aur baaki udhar.",
    "Pappu bhai ne 750 ka maal liya, 250 cash diya aur 500 kal dega.",
]

# Mapping for demo quick-select buttons — specific transcript per index
DEMO_TRANSCRIPT_MAP = {
    0: "Sharma ji ne 450 ka rashan liya, 200 cash diya baaki kal denge.",
    1: "Ramesh bhai ne 1200 ka saman liya, pura UPI kar diya.",
    2: "Sita ji ka purana udhar 800 tha, 500 cash de diya.",
    3: "Mohan ne 600 ka kirana liya, pura udhar likh do.",
    4: "Gupta ji ne 950 ka maal liya, 450 cash aur 500 UPI kiya.",
}


# ── Provider Interface ─────────────────────────────────────────────────────────

class ASRProvider(ABC):
    """Abstract base class for ASR providers."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, content_type: str) -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio data
            content_type: MIME type (audio/webm, audio/wav)

        Returns:
            Transcribed text string

        Raises:
            ASRError: If transcription fails
        """
        ...


class ASRError(Exception):
    """Raised when ASR transcription fails."""
    def __init__(self, message: str, code: str = "ERR_TRANSCRIPTION_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


# ── Mock Provider ──────────────────────────────────────────────────────────────

class MockASRProvider(ASRProvider):
    """Returns realistic Hinglish transcripts without any external API.
    Supports both random selection and indexed demo selection."""

    def __init__(self):
        self._index = 0

    def transcribe(self, audio_bytes: bytes, content_type: str) -> str:
        """Return a rotating mock Hinglish transcript."""
        transcript = MOCK_TRANSCRIPTS[self._index % len(MOCK_TRANSCRIPTS)]
        self._index += 1
        return transcript

    def get_demo_transcript(self, index: int) -> str:
        """Get a specific demo transcript by index."""
        return DEMO_TRANSCRIPT_MAP.get(index, MOCK_TRANSCRIPTS[0])


# ── OpenAI Whisper Provider ────────────────────────────────────────────────────

class OpenAIWhisperProvider(ASRProvider):
    """Transcribe audio using OpenAI Whisper API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(self, audio_bytes: bytes, content_type: str) -> str:
        """Send audio to OpenAI Whisper API for transcription."""
        try:
            import httpx

            # Determine file extension from content type
            ext_map = {"audio/webm": "webm", "audio/wav": "wav", "audio/mpeg": "mp3"}
            ext = ext_map.get(content_type, "webm")

            response = httpx.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (f"audio.{ext}", audio_bytes, content_type)},
                data={
                    "model": "whisper-1",
                    "language": "hi",
                    "response_format": "text",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.text.strip()

        except ImportError:
            raise ASRError("httpx package required for OpenAI provider", "ERR_TRANSCRIPTION_FAILED")
        except Exception as e:
            raise ASRError(f"OpenAI Whisper transcription failed: {str(e)}", "ERR_TRANSCRIPTION_FAILED")


# ── Groq Whisper Provider ─────────────────────────────────────────────────────

class GroqWhisperProvider(ASRProvider):
    """Transcribe audio using Groq's Whisper-compatible API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def transcribe(self, audio_bytes: bytes, content_type: str) -> str:
        """Send audio to Groq Whisper API for transcription."""
        try:
            import httpx

            ext_map = {"audio/webm": "webm", "audio/wav": "wav", "audio/mpeg": "mp3"}
            ext = ext_map.get(content_type, "webm")

            response = httpx.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (f"audio.{ext}", audio_bytes, content_type)},
                data={
                    "model": "whisper-large-v3",
                    "language": "hi",
                    "response_format": "text",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.text.strip()

        except ImportError:
            raise ASRError("httpx package required for Groq provider", "ERR_TRANSCRIPTION_FAILED")
        except Exception as e:
            raise ASRError(f"Groq Whisper transcription failed: {str(e)}", "ERR_TRANSCRIPTION_FAILED")


# ── Audio Validation ───────────────────────────────────────────────────────────

ALLOWED_CONTENT_TYPES = {"audio/webm", "audio/wav", "audio/mpeg", "audio/ogg", "audio/mp4"}


def validate_audio(
    audio_bytes: bytes,
    content_type: str,
    max_size_mb: int = 10,
) -> None:
    """Validate audio input before sending to ASR.

    Raises ASRError on validation failure.
    """
    if not audio_bytes or len(audio_bytes) == 0:
        raise ASRError("Audio file is empty.", "ERR_AUDIO_EMPTY")

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ASRError(
            f"Unsupported audio type: {content_type}. Accepted: {', '.join(ALLOWED_CONTENT_TYPES)}",
            "ERR_AUDIO_INVALID",
        )

    max_bytes = max_size_mb * 1024 * 1024
    if len(audio_bytes) > max_bytes:
        raise ASRError(
            f"Audio file too large ({len(audio_bytes)} bytes). Maximum: {max_bytes} bytes.",
            "ERR_AUDIO_INVALID",
        )


# ── Provider Factory ──────────────────────────────────────────────────────────

def get_asr_provider(settings: Settings) -> ASRProvider:
    """Factory: create the appropriate ASR provider based on configuration."""
    provider = settings.ASR_PROVIDER.lower()

    if provider == "mock":
        return MockASRProvider()
    elif provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ASRError("OPENAI_API_KEY is required for OpenAI ASR provider", "ERR_TRANSCRIPTION_FAILED")
        return OpenAIWhisperProvider(settings.OPENAI_API_KEY)
    elif provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ASRError("GROQ_API_KEY is required for Groq ASR provider", "ERR_TRANSCRIPTION_FAILED")
        return GroqWhisperProvider(settings.GROQ_API_KEY)
    else:
        raise ASRError(f"Unknown ASR provider: {provider}", "ERR_TRANSCRIPTION_FAILED")
