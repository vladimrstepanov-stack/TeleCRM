"""Интерпретация сообщения через DeepSeek (AiTunnel, OpenAI-совместимый API)."""

import json
import logging

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.ai.prompts import SYSTEM_PROMPT
from app.ai.schemas import LLMResult

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 6000


class LLMParseError(Exception):
    """Ответ модели не удалось привести к строгой схеме."""


class DeepSeekParser:
    """Классифицирует intent и извлекает сущности строго по Pydantic-схеме."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def parse(self, user_text: str) -> LLMResult:
        text = user_text.strip()[:MAX_INPUT_CHARS]
        logger.info("LLM: запрос интерпретации, %d символов", len(text))

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                # Текст пользователя идёт отдельным сообщением и не смешивается
                # с системными правилами — так его нельзя выдать за инструкцию.
                {"role": "user", "content": text},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("LLM: ответ не является JSON")
            raise LLMParseError("Модель вернула не-JSON ответ") from exc

        try:
            result = LLMResult.model_validate(payload)
        except ValidationError as exc:
            # Логируем только пути и типы ошибок (loc/type), без значений полей,
            # чтобы причина была видна в error.log и при этом данные не утекали.
            problems = [
                {"loc": ".".join(str(p) for p in err["loc"]), "type": err["type"]}
                for err in exc.errors()
            ]
            logger.error("LLM: ответ не прошёл валидацию схемы: %s", problems)
            raise LLMParseError("Ответ модели не соответствует схеме") from exc

        logger.info("LLM: intent=%s", result.intent.value)
        return result
