"""Structured output enforcement using instructor + Pydantic retry."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, TypeVar

import structlog
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from core.llm_client import LLMClient

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class OutputEnforcer:
    """
    Wraps LLM calls to guarantee a valid Pydantic model is returned.

    On validation failure, provides corrective feedback to the model
    and retries up to `max_retries` times.
    """

    def __init__(self, llm_client: LLMClient, max_retries: int = 3) -> None:
        self.llm_client = llm_client
        self.max_retries = max_retries

    async def enforce(
        self,
        messages: list[dict[str, str]],
        output_schema: type[T],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> T:
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        instruction = (
            f"\n\nIMPORTANT: You MUST respond with a single valid JSON object "
            f"that conforms exactly to this JSON schema:\n{schema_json}\n"
            f"Do not include any text, markdown, or explanation outside the JSON object."
        )

        # Inject schema instruction into the system message
        working_messages: list[dict[str, str]] = []
        injected = False
        for msg in messages:
            if msg["role"] == "system" and not injected:
                working_messages.append(
                    {"role": "system", "content": msg["content"] + instruction}
                )
                injected = True
            else:
                working_messages.append(dict(msg))
        if not injected:
            working_messages.insert(0, {"role": "system", "content": instruction})

        last_error: Exception | None = None
        last_raw: str = ""

        for attempt in range(1, self.max_retries + 1):
            try:
                raw = await self.llm_client.complete(
                    working_messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    **kwargs,
                )
                last_raw = raw
                parsed = json.loads(raw)
                return output_schema.model_validate(parsed)

            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "Structured output validation failed",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    schema=output_schema.__name__,
                    error=str(exc),
                )
                if attempt < self.max_retries:
                    # Feed corrective context back to the model
                    working_messages.append(
                        {"role": "assistant", "content": last_raw}
                    )
                    working_messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Your response failed validation with: {exc}. "
                                f"Please correct it and return only a valid JSON object "
                                f"matching the schema."
                            ),
                        }
                    )

        raise ValueError(
            f"Failed to produce valid {output_schema.__name__} after "
            f"{self.max_retries} attempts. Last error: {last_error}"
        )
