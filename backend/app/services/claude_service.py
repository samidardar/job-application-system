"""
LLM service using Google Gemini 2.5 Flash — replaces Anthropic Claude.
Same interface as the original ClaudeService so all callers work unchanged.

Model: gemini-2.5-flash-preview-04-17
Features:
- Async via google.generativeai async API
- Structured JSON output with Pydantic validation
- Retry with exponential backoff on rate limit / connection errors
- Daily token budget guard
"""
import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from typing import Type, TypeVar

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MODEL = "gemini-2.5-flash-preview-04-17"

# ── Daily token budget guard ──────────────────────────────────────────────────
_DAILY_TOKEN_LIMIT = int(getattr(settings, "gemini_daily_token_limit", 5_000_000))
_token_usage: dict[str, int] = defaultdict(int)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _record_tokens(total: int) -> None:
    _token_usage[_today()] += total


def _check_budget() -> None:
    used = _token_usage[_today()]
    if used >= _DAILY_TOKEN_LIMIT:
        raise RuntimeError(
            f"Daily Gemini token budget exceeded ({used:,}/{_DAILY_TOKEN_LIMIT:,} tokens). "
            "Increase GEMINI_DAILY_TOKEN_LIMIT or wait until tomorrow."
        )


# ── Service ───────────────────────────────────────────────────────────────────

class ClaudeService:
    """Gemini-backed LLM service — drop-in replacement for the old ClaudeService."""

    def __init__(self):
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Get one free at https://aistudio.google.com/app/apikey"
            )
        genai.configure(api_key=settings.gemini_api_key)
        self.model_name = MODEL

    def _make_model(self, system: str) -> genai.GenerativeModel:
        return genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ResourceExhausted, ServiceUnavailable)),
        reraise=True,
    )
    async def complete(
        self,
        system: str,
        user: str,
        output_schema: Type[T] | None = None,
        max_tokens: int = 4096,
    ) -> tuple[T | str, int, int]:
        """
        Call Gemini and return (parsed_response, prompt_tokens, completion_tokens).
        Same signature as the original ClaudeService.complete().
        """
        _check_budget()

        if output_schema:
            schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
            system_prompt = (
                f"{system}\n\n"
                "IMPORTANT: Respond ONLY with a valid JSON object matching this exact schema. "
                "No markdown, no explanation, no text outside the JSON object.\n"
                f"Schema:\n{schema_json}"
            )
        else:
            system_prompt = system

        model = self._make_model(system_prompt)

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                user,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.3,
                ),
            ),
        )

        # Token counting
        try:
            prompt_tokens = response.usage_metadata.prompt_token_count or 0
            completion_tokens = response.usage_metadata.candidates_token_count or 0
            _record_tokens(prompt_tokens + completion_tokens)
        except Exception:
            prompt_tokens = 0
            completion_tokens = 0

        raw_text = response.text

        if output_schema:
            parsed = self._parse_structured(raw_text, output_schema)
            return parsed, prompt_tokens, completion_tokens

        return raw_text, prompt_tokens, completion_tokens

    def _parse_structured(self, raw_text: str, schema: Type[T]) -> T:
        """Extract and validate JSON from LLM response."""
        clean = raw_text.strip()

        # Strip markdown code fences
        if "```" in clean:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean)
            if match:
                clean = match.group(1).strip()

        # Find first { ... } block
        brace_match = re.search(r"\{[\s\S]*\}", clean)
        if brace_match:
            clean = brace_match.group(0)

        try:
            data = json.loads(clean)
            return schema.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {schema.__name__}: {e}\nRaw: {raw_text[:600]}")
            raise ValueError(f"LLM returned invalid JSON: {e}") from e
        except Exception as e:
            logger.error(f"Schema validation error for {schema.__name__}: {e}")
            raise ValueError(f"LLM response schema mismatch: {e}") from e

    async def complete_text(
        self, system: str, user: str, max_tokens: int = 4096
    ) -> tuple[str, int, int]:
        return await self.complete(system, user, output_schema=None, max_tokens=max_tokens)

    async def complete_structured(
        self,
        system: str,
        user: str,
        output_schema: Type[T],
        max_tokens: int = 4096,
    ) -> tuple[T, int, int]:
        result, pt, ct = await self.complete(system, user, output_schema, max_tokens)
        return result, pt, ct  # type: ignore[return-value]


# Singleton — one instance per worker process
_service_instance: ClaudeService | None = None


def get_claude_service() -> ClaudeService:
    global _service_instance
    if _service_instance is None:
        _service_instance = ClaudeService()
    return _service_instance
