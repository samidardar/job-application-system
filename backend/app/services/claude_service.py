"""
LLM service using Claude Sonnet 4.6 — SOTA quality for CV tailoring, matching, and cover letters.
"""
import json
import logging
import re
from typing import Type, TypeVar
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MODEL = "claude-sonnet-4-6"


class ClaudeService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = MODEL

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError)),
    )
    async def complete(
        self,
        system: str,
        user: str,
        output_schema: Type[T] | None = None,
        max_tokens: int = 4096,
    ) -> tuple[T | str, int, int]:
        """
        Call Claude Haiku and return (parsed_response, prompt_tokens, completion_tokens).
        If output_schema is provided, validates and returns a Pydantic model instance.
        """
        if output_schema:
            schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
            system_prompt = (
                f"{system}\n\n"
                f"IMPORTANT: Respond ONLY with a valid JSON object matching this exact schema. "
                f"No markdown, no explanation, no text outside the JSON object.\n"
                f"Schema:\n{schema_json}"
            )
        else:
            system_prompt = system

        # Use sync client in thread pool to avoid blocking (Anthropic SDK is sync)
        import asyncio
        response = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user}],
            )
        )

        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
        raw_text = response.content[0].text

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

        # Find first { ... } block in case there's preamble
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


# Singleton
_service_instance: ClaudeService | None = None


def get_claude_service() -> ClaudeService:
    global _service_instance
    if _service_instance is None:
        _service_instance = ClaudeService()
    return _service_instance
