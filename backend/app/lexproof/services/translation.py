"""Machine translation for AI findings, so a non-English-speaking reviewer
can read a finding's title/description/recommendation/playbook comparison in
their own language.

Per this engagement's "stub-now, wire in real credentials later" scope
decision, applied a little differently here than for e-signature or chat
notifications: there is no meaningful "not really translating" stub for a
translation feature, so instead of a fake placeholder, the always-available
default path (`GeminiTranslationProvider`) is a genuinely working
translation using the same Gemini/Vertex AI provider this app already has
fully configured for contract analysis -- no new credential is needed for
the feature to work today. `GoogleTranslateProvider` is the "real
integration point": a complete, production-grade Google Cloud Translation
API v2 integration that activates automatically the moment a
`GOOGLE_TRANSLATE_API_KEY` is configured, without any code change, exactly
mirroring how `get_esignature_provider()` switches from the stub to
DocuSign in `esignature.py`.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from ..config import LexProofSettings, get_settings
from ..repositories.firestore import FirestoreRepository
from .vertex_ai import VertexAIError, VertexGeminiProvider

logger = logging.getLogger(__name__)

TRANSLATIONS_COLLECTION = "finding_translations"

# Target languages the UI offers. Codes are BCP-47 / ISO 639-1, matched by
# both translation providers.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "zh": "Chinese (Simplified)",
    "ja": "Japanese",
    "hi": "Hindi",
    "ar": "Arabic",
}

TRANSLATED_FIELDS = ("title", "description", "recommendation", "playbook_notes")


class TranslationError(ValueError):
    """Base error for translation requests."""


class TranslationProvider(Protocol):
    name: str

    async def translate_texts(self, texts: list[str], target_language: str) -> list[str]: ...


class GeminiTranslationProvider:
    """Default provider: uses the app's already-configured Gemini/Vertex AI
    client, so translation works today with zero additional credentials."""

    name = "gemini"

    SCHEMA = {
        "type": "object",
        "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
        "required": ["translations"],
    }

    def __init__(self, *, llm: Any = None) -> None:
        self.llm = llm or VertexGeminiProvider()

    async def translate_texts(self, texts: list[str], target_language: str) -> list[str]:
        language_name = SUPPORTED_LANGUAGES.get(target_language, target_language)
        if not any(text.strip() for text in texts):
            return list(texts)
        import json

        prompt = (
            f"Translate each string in this JSON array into {language_name}. Preserve the exact array order and "
            "length -- return exactly one translation per input string, translating an empty string to an empty "
            "string. Do not add commentary, explanations, or quotation marks around the translations; return only "
            "the natural-language translation of each string's meaning, preserving its tone as legal/business "
            f"language.\n\nInput array:\n{json.dumps(texts)}"
        )
        try:
            result = await self.llm.complete_json(
                prompt, self.SCHEMA, system_prompt="You are a precise legal-document translator."
            )
        except VertexAIError:
            raise
        except Exception as exc:
            raise TranslationError(f"Translation failed: {exc}") from exc
        translations = result.get("translations")
        if not isinstance(translations, list) or len(translations) != len(texts):
            raise TranslationError("Translation provider returned a mismatched number of results")
        return [str(item) for item in translations]


class GoogleTranslateProvider:
    """Real Google Cloud Translation API v2 integration (API-key auth).
    Inert until GOOGLE_TRANSLATE_API_KEY is configured --
    `get_translation_provider()` only ever constructs this once that is
    true."""

    name = "google_translate"
    API_URL = "https://translation.googleapis.com/language/translate/v2"

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def translate_texts(self, texts: list[str], target_language: str) -> list[str]:
        non_empty_indexes = [index for index, text in enumerate(texts) if text.strip()]
        if not non_empty_indexes:
            return list(texts)
        payload = {
            "q": [texts[index] for index in non_empty_indexes],
            "target": target_language,
            "format": "text",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.API_URL, params={"key": self.api_key}, json=payload)
        if response.status_code != 200:
            raise TranslationError(f"Google Translate request failed: {response.text}")
        body = response.json()
        translated = [item["translatedText"] for item in body["data"]["translations"]]
        results = list(texts)
        for offset, index in enumerate(non_empty_indexes):
            results[index] = translated[offset]
        return results


def get_translation_provider(settings: LexProofSettings | None = None) -> TranslationProvider:
    settings = settings or get_settings()
    if settings.has_google_translate_configuration():
        return GoogleTranslateProvider(api_key=settings.google_translate_api_key.get_secret_value())
    return GeminiTranslationProvider()


class TranslationService:
    def __init__(
        self,
        *,
        findings: FirestoreRepository | None = None,
        translations: FirestoreRepository | None = None,
        provider: TranslationProvider | None = None,
    ) -> None:
        self.findings = findings or FirestoreRepository("risk_findings")
        self.translations = translations or FirestoreRepository(TRANSLATIONS_COLLECTION)
        self.provider = provider or get_translation_provider()

    @staticmethod
    def _cache_id(finding_id: str, target_language: str) -> str:
        return f"{finding_id}_{target_language}"

    async def translate_findings(
        self, finding_ids: list[str], target_language: str, user_id: str
    ) -> dict[str, dict[str, Any]]:
        if target_language not in SUPPORTED_LANGUAGES:
            raise TranslationError(f"Unsupported target language: {target_language}")
        if not finding_ids:
            return {}

        results: dict[str, dict[str, Any]] = {}
        to_fetch: list[tuple[str, dict[str, Any]]] = []

        for finding_id in finding_ids:
            finding = self.findings.get(finding_id)
            if not finding:
                continue
            owner_id = finding.get("owner_id")
            if owner_id and owner_id != user_id:
                continue
            cached = self.translations.get(self._cache_id(finding_id, target_language))
            if cached:
                results[finding_id] = {field: cached.get(field) for field in TRANSLATED_FIELDS}
                results[finding_id]["target_language"] = target_language
                continue
            to_fetch.append((finding_id, finding))

        if to_fetch:
            flattened: list[str] = []
            for _finding_id, finding in to_fetch:
                for field in TRANSLATED_FIELDS:
                    flattened.append(str(finding.get(field) or ""))

            translated_flat = await self.provider.translate_texts(flattened, target_language)

            for position, (finding_id, _finding) in enumerate(to_fetch):
                start = position * len(TRANSLATED_FIELDS)
                slice_ = translated_flat[start:start + len(TRANSLATED_FIELDS)]
                translated_record = dict(zip(TRANSLATED_FIELDS, slice_))
                self.translations.set(
                    self._cache_id(finding_id, target_language),
                    {
                        "finding_id": finding_id,
                        "target_language": target_language,
                        "provider": self.provider.name,
                        **translated_record,
                    },
                )
                results[finding_id] = {**translated_record, "target_language": target_language}

        return results


_translation_service: TranslationService | None = None


def get_translation_service() -> TranslationService:
    global _translation_service
    if _translation_service is None:
        _translation_service = TranslationService()
    return _translation_service
