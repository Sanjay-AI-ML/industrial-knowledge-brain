"""Multilingual voice interaction pipeline for field technicians.

Flow
----
1. **STT** — ``faster-whisper`` transcribes the uploaded audio, auto-detecting
   the spoken language (Hindi, Tamil, Telugu, English, etc.).
2. **Translation (Indic → English)** — if the detected language is not English,
   translate the transcript to English via Bhashini's NMT API.  Falls back to
   Google Gemini if Bhashini is unconfigured / unreachable.
3. **RAG** — the English query is fed into :class:`RAGEngine` from Phase 2.
4. **Back-translation (English → Indic)** — the English answer is translated
   back to the original language via the same translation path.
5. **TTS (optional)** — Bhashini's TTS API converts the translated answer to
   spoken audio (base64-encoded WAV).  Returns ``None`` gracefully if TTS fails.

Bhashini API auth
-----------------
* **Pipeline Config** endpoint returns a ``callbackUrl`` + ``inferenceApiKey``.
* **Pipeline Compute** endpoint (at that callbackUrl) performs translation / TTS.
* If ``bhashini_api_key`` is still ``"REPLACE_ME"`` we skip Bhashini entirely and
  use the Gemini-based fallback translator (which supports all major Indian
  languages at high accuracy).
"""

from __future__ import annotations

import base64
import io
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.core.rag_engine import RAGEngine
from app.models.schemas import UserRole

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bhashini language codes  (ISO 639-1 → Bhashini codes)
# ---------------------------------------------------------------------------
# faster-whisper returns ISO 639-1 codes; Bhashini uses the same set.
SUPPORTED_INDIC_LANGS = {
    "hi", "ta", "te", "bn", "mr", "gu", "kn", "ml", "pa", "or", "as", "ur",
}

# Map faster-whisper language names to ISO codes (it uses full names internally
# but returns ISO codes via ``info.language``).
LANG_NAMES: dict[str, str] = {
    "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "bn": "Bengali",
    "mr": "Marathi", "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam",
    "pa": "Punjabi", "or": "Odia", "as": "Assamese", "ur": "Urdu",
    "en": "English",
}

BHASHINI_CONFIG_URL = (
    "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
)
BHASHINI_PIPELINE_ID = "64392f96daac500b55c543cd"

# Timeout for Bhashini HTTP calls (seconds).
_BHASHINI_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class VoiceResult:
    """Structured result of the full voice pipeline."""

    transcript: str = ""
    detected_language: str = "en"
    detected_language_name: str = "English"
    query_english: str = ""
    answer_english: str = ""
    answer_translated: str = ""
    audio_response_base64: str | None = None
    translation_method: str = "none"  # "bhashini" | "gemini" | "none"
    confidence: str = "low"
    sources: list[dict[str, Any]] = field(default_factory=list)
    related_entities: list[dict[str, Any]] = field(default_factory=list)
    session_id: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Voice pipeline
# ---------------------------------------------------------------------------
class VoicePipeline:
    """End-to-end multilingual voice query pipeline."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._whisper_model = None
        self._rag = RAGEngine(self.settings)
        self._http = httpx.Client(timeout=_BHASHINI_TIMEOUT)

    # ------------------------------------------------------------------ #
    # Lazy-load faster-whisper model
    # ------------------------------------------------------------------ #
    @property
    def whisper(self):
        """Lazily load the faster-whisper model on first use."""
        if self._whisper_model is None:
            from faster_whisper import WhisperModel

            logger.info(
                "Loading faster-whisper model '%s' on %s (%s)…",
                self.settings.whisper_model_size,
                self.settings.whisper_device,
                self.settings.whisper_compute_type,
            )
            self._whisper_model = WhisperModel(
                self.settings.whisper_model_size,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )
        return self._whisper_model

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def process_audio(
        self,
        audio_bytes: bytes,
        role: UserRole = UserRole.ENGINEER,
        session_id: str | None = None,
    ) -> VoiceResult:
        """Run the full pipeline: STT → translate → RAG → back-translate → TTS.

        Never raises — all failures are captured in ``VoiceResult.error``.
        """
        result = VoiceResult(session_id=session_id or str(uuid.uuid4()))

        # --- 1.  Speech-to-text -----------------------------------------
        try:
            transcript, lang_code = self._transcribe(audio_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.exception("STT failed")
            result.error = f"Speech-to-text failed: {exc}"
            return result

        result.transcript = transcript
        result.detected_language = lang_code
        result.detected_language_name = LANG_NAMES.get(lang_code, lang_code)

        if not transcript.strip():
            result.error = "No speech detected in audio."
            return result

        # --- 2.  Translate to English (if needed) -----------------------
        if lang_code == "en":
            result.query_english = transcript
            result.translation_method = "none"
        else:
            try:
                eng_text, method = self._translate_to_english(transcript, lang_code)
                result.query_english = eng_text
                result.translation_method = method
            except Exception as exc:  # noqa: BLE001
                logger.exception("Translation to English failed")
                # Fallback: send the original transcript to RAG (may work if
                # partially English / technical terms).
                result.query_english = transcript
                result.translation_method = "none"
                result.error = f"Translation failed (using raw transcript): {exc}"

        # --- 3.  RAG query ----------------------------------------------
        try:
            rag_response = self._rag.query(
                question=result.query_english,
                role=role,
                session_id=result.session_id,
            )
            result.answer_english = rag_response.answer
            result.confidence = rag_response.confidence.value
            result.session_id = rag_response.session_id
            result.sources = [
                {
                    "doc_name": s.doc_name,
                    "snippet": s.snippet,
                    "relevance_score": s.relevance_score,
                }
                for s in rag_response.sources
            ]
            result.related_entities = [
                {"label": e.label, "value": e.value, "relationship": e.relationship}
                for e in rag_response.related_entities
            ]
        except Exception as exc:  # noqa: BLE001
            logger.exception("RAG query failed")
            result.answer_english = "I couldn't process your question right now."
            result.error = f"RAG query failed: {exc}"

        # --- 4.  Back-translate to original language --------------------
        if lang_code == "en":
            result.answer_translated = result.answer_english
        else:
            try:
                result.answer_translated, _ = self._translate_from_english(
                    result.answer_english, lang_code,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Back-translation failed; returning English.")
                result.answer_translated = result.answer_english

        # --- 5.  TTS (optional) -----------------------------------------
        if lang_code != "en" and self._bhashini_available():
            try:
                audio_b64 = self._tts(result.answer_translated, lang_code)
                result.audio_response_base64 = audio_b64
            except Exception:  # noqa: BLE001
                logger.debug("Bhashini TTS failed — skipping audio response.")

        return result

    # ================================================================== #
    # STT — faster-whisper
    # ================================================================== #
    def _transcribe(self, audio_bytes: bytes) -> tuple[str, str]:
        """Transcribe audio bytes → (transcript_text, iso_lang_code)."""
        # Write to a temp file because faster-whisper needs a file path.
        suffix = ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            segments, info = self.whisper.transcribe(
                tmp_path,
                beam_size=5,
                language=None,  # auto-detect
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments)
            lang = info.language  # ISO 639-1 code
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        logger.info(
            "STT result: lang=%s (prob=%.2f), text='%s…'",
            lang,
            info.language_probability,
            text[:80],
        )
        return text, lang

    # ================================================================== #
    # Translation helpers
    # ================================================================== #
    def _bhashini_available(self) -> bool:
        """True if Bhashini credentials are configured (not placeholder)."""
        return (
            self.settings.bhashini_api_key != "REPLACE_ME"
            and self.settings.bhashini_user_id != "REPLACE_ME"
        )

    def _translate_to_english(
        self, text: str, source_lang: str,
    ) -> tuple[str, str]:
        """Translate Indic text → English.  Returns (translated_text, method)."""
        if self._bhashini_available():
            try:
                translated = self._bhashini_translate(text, source_lang, "en")
                return translated, "bhashini"
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Bhashini translate failed; falling back to Gemini.",
                    exc_info=True,
                )

        # Gemini fallback
        translated = self._gemini_translate(text, source_lang, "en")
        return translated, "gemini"

    def _translate_from_english(
        self, text: str, target_lang: str,
    ) -> tuple[str, str]:
        """Translate English → Indic.  Returns (translated_text, method)."""
        if self._bhashini_available():
            try:
                translated = self._bhashini_translate(text, "en", target_lang)
                return translated, "bhashini"
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Bhashini back-translate failed; falling back to Gemini.",
                    exc_info=True,
                )

        translated = self._gemini_translate(text, "en", target_lang)
        return translated, "gemini"

    # ------------------------------------------------------------------ #
    # Bhashini translation
    # ------------------------------------------------------------------ #
    def _bhashini_get_config(
        self, task_types: list[dict[str, Any]],
    ) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
        """Call Bhashini pipeline config → (callbackUrl, auth_headers, configs).

        Raises on failure so callers can fall back.
        """
        headers = {
            "userID": self.settings.bhashini_user_id,
            "ulcaApiKey": self.settings.bhashini_api_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "pipelineTasks": task_types,
            "pipelineRequestConfig": {"pipelineId": BHASHINI_PIPELINE_ID},
        }

        resp = self._http.post(BHASHINI_CONFIG_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        # Extract inference endpoint
        endpoint = data.get("pipelineInferenceAPIEndPoint", {})
        callback_url = endpoint.get("callbackUrl", "")
        inf_key = endpoint.get("inferenceApiKey", {})
        auth_headers = {
            inf_key.get("name", "Authorization"): inf_key.get("value", ""),
        }

        # Extract per-task configs (serviceIds etc.)
        configs = data.get("pipelineResponseConfig", [])
        return callback_url, auth_headers, configs

    def _bhashini_translate(
        self, text: str, source_lang: str, target_lang: str,
    ) -> str:
        """Translate via Bhashini NMT.  Raises on failure."""
        task_config = [
            {
                "taskType": "translation",
                "config": {
                    "language": {
                        "sourceLanguage": source_lang,
                        "targetLanguage": target_lang,
                    },
                },
            },
        ]
        callback_url, auth_headers, configs = self._bhashini_get_config(task_config)

        # Find the translation serviceId from the config response
        service_id = ""
        for cfg in configs:
            if cfg.get("taskType") == "translation":
                config_list = cfg.get("config", [])
                if config_list:
                    service_id = config_list[0].get("serviceId", "")
                break

        compute_payload = {
            "pipelineTasks": [
                {
                    "taskType": "translation",
                    "config": {
                        "language": {
                            "sourceLanguage": source_lang,
                            "targetLanguage": target_lang,
                        },
                        "serviceId": service_id,
                    },
                },
            ],
            "inputData": {
                "input": [{"source": text}],
            },
        }

        resp = self._http.post(
            callback_url, json=compute_payload, headers=auth_headers,
        )
        resp.raise_for_status()
        data = resp.json()

        # Parse the translated output
        outputs = data.get("pipelineResponse", [])
        for out in outputs:
            for item in out.get("output", []):
                target = item.get("target", "")
                if target:
                    return target

        raise ValueError("Bhashini returned no translated text.")

    # ------------------------------------------------------------------ #
    # Bhashini TTS
    # ------------------------------------------------------------------ #
    def _tts(self, text: str, lang: str) -> str | None:
        """Convert text to speech via Bhashini TTS.  Returns base64 audio."""
        task_config = [
            {
                "taskType": "tts",
                "config": {
                    "language": {"sourceLanguage": lang},
                },
            },
        ]
        callback_url, auth_headers, configs = self._bhashini_get_config(task_config)

        service_id = ""
        for cfg in configs:
            if cfg.get("taskType") == "tts":
                config_list = cfg.get("config", [])
                if config_list:
                    service_id = config_list[0].get("serviceId", "")
                break

        compute_payload = {
            "pipelineTasks": [
                {
                    "taskType": "tts",
                    "config": {
                        "language": {"sourceLanguage": lang},
                        "serviceId": service_id,
                        "gender": "female",
                    },
                },
            ],
            "inputData": {
                "input": [{"source": text}],
            },
        }

        resp = self._http.post(
            callback_url, json=compute_payload, headers=auth_headers,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract base64-encoded audio from the response
        outputs = data.get("pipelineResponse", [])
        for out in outputs:
            for item in out.get("audio", []):
                audio_b64 = item.get("audioContent", "")
                if audio_b64:
                    return audio_b64

        return None

    # ------------------------------------------------------------------ #
    # Gemini fallback translator
    # ------------------------------------------------------------------ #
    def _gemini_translate(
        self, text: str, source_lang: str, target_lang: str,
    ) -> str:
        """Use Google Gemini to translate between languages (fallback path).

        Works for all major Indian languages with high quality.
        """
        from google import genai
        from google.genai import types as genai_types

        src_name = LANG_NAMES.get(source_lang, source_lang)
        tgt_name = LANG_NAMES.get(target_lang, target_lang)

        prompt = (
            f"Translate the following text from {src_name} to {tgt_name}. "
            f"Return ONLY the translated text, with no commentary, labels, or "
            f"quotation marks.\n\n"
            f"Text:\n{text}"
        )

        client = genai.Client(api_key=self.settings.gemini_api_key)
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=2048,
            ),
        )

        translated = getattr(response, "text", None)
        if not translated:
            raise RuntimeError("Gemini returned no translation.")

        return translated.strip()


# Module-level convenience instance.
voice_pipeline = VoicePipeline()
