import json
import logging
from typing import Any, Type, TypeVar
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
    ) -> tuple[T | dict | str, int, int]:
        """
        Call Claude and return (parsed_response, prompt_tokens, completion_tokens).
        If output_schema is provided, validates and returns a Pydantic model instance.
        """
        messages = [{"role": "user", "content": user}]

        if output_schema:
            # Ask Claude to respond with valid JSON matching the schema
            schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
            system_with_schema = (
                f"{system}\n\n"
                f"IMPORTANT: Respond ONLY with a valid JSON object matching this schema:\n"
                f"```json\n{schema_json}\n```\n"
                f"Do not include any text outside the JSON object."
            )
        else:
            system_with_schema = system

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_with_schema,
            messages=messages,
        )

        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
        raw_text = response.content[0].text

        if output_schema:
            # Extract JSON from response (handle markdown code blocks)
            clean = raw_text.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1])
            try:
                data = json.loads(clean)
                parsed = output_schema.model_validate(data)
                return parsed, prompt_tokens, completion_tokens
            except Exception as e:
                logger.error(f"Failed to parse Claude response as {output_schema.__name__}: {e}")
                logger.debug(f"Raw response: {raw_text[:500]}")
                raise ValueError(f"Claude response parsing failed: {e}") from e

        return raw_text, prompt_tokens, completion_tokens

    async def complete_text(self, system: str, user: str, max_tokens: int = 4096) -> tuple[str, int, int]:
        return await self.complete(system, user, output_schema=None, max_tokens=max_tokens)

    async def complete_structured(
        self,
        system: str,
        user: str,
        output_schema: Type[T],
        max_tokens: int = 4096,
    ) -> tuple[T, int, int]:
        result, pt, ct = await self.complete(system, user, output_schema, max_tokens)
        return result, pt, ct


# Singleton
_claude_service: ClaudeService | None = None


def get_claude_service() -> ClaudeService:
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service
