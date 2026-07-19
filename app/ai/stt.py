"""Распознавание речи через qwen3-asr-flash (AiTunnel, OpenAI-совместимый API)."""

import logging
from pathlib import Path

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class SpeechToText:
    """Тонкая обёртка над OpenAI-совместимым эндпоинтом транскрипции AiTunnel."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def transcribe(self, audio_path: Path) -> str:
        """Возвращает текст из аудиофайла. Файл читается локально и не хранится."""
        logger.info("STT: старт транскрипции модели %s", self._model)
        with audio_path.open("rb") as audio_file:
            response = await self._client.audio.transcriptions.create(
                model=self._model,
                file=audio_file,
            )
        text = (response.text or "").strip()
        logger.info("STT: получено %d символов", len(text))
        return text
