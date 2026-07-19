"""Оркестрация приёма сообщения: голос -> текст -> интерпретация LLM."""

import logging
from pathlib import Path

from app.ai.deepseek import DeepSeekParser
from app.ai.schemas import LLMResult
from app.ai.stt import SpeechToText

logger = logging.getLogger(__name__)


class Intake:
    """Связывает распознавание речи и разбор текста в единый вход пайплайна."""

    def __init__(self, stt: SpeechToText, parser: DeepSeekParser) -> None:
        self._stt = stt
        self._parser = parser

    async def transcribe(self, audio_path: Path) -> str:
        return await self._stt.transcribe(audio_path)

    async def interpret(self, text: str) -> LLMResult:
        return await self._parser.parse(text)
