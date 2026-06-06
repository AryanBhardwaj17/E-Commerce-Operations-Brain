"""Resilient async LLM client — supports Azure OpenAI, standard OpenAI, and Ollama."""
from __future__ import annotations

from typing import Any

import structlog
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncAzureOpenAI,
    AsyncOpenAI,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.settings import AppSettings, get_settings

logger = structlog.get_logger(__name__)

_RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError)


def _build_async_client(settings: AppSettings | None = None) -> AsyncOpenAI:
    """
    Build the correct AsyncOpenAI-compatible client based on LLM_PROVIDER env var.

    - ``azure``  → AsyncAzureOpenAI using AZURE_OPENAI_* vars
    - ``ollama`` → AsyncOpenAI pointed at the local Ollama OpenAI-compat endpoint
    - ``openai`` → Standard AsyncOpenAI (default)
    """
    app_settings = settings or get_settings()
    provider = app_settings.llm_provider

    if provider == "azure":
        if not app_settings.azure_openai_endpoint or not app_settings.azure_openai_api_key:
            raise RuntimeError(
                "Azure OpenAI requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."
            )
        return AsyncAzureOpenAI(
            azure_endpoint=app_settings.azure_openai_endpoint,
            api_key=app_settings.azure_openai_api_key,
            api_version=app_settings.openai_api_version,
        )

    if provider == "ollama":
        return AsyncOpenAI(
            base_url=app_settings.ollama_base_url,
            api_key="ollama",  # Ollama ignores the key but the SDK requires a non-empty value
        )

    # default: standard OpenAI
    if not app_settings.openai_api_key:
        raise RuntimeError("OpenAI requires OPENAI_API_KEY.")
    return AsyncOpenAI(api_key=app_settings.openai_api_key)


def _default_model(settings: AppSettings | None = None) -> str:
    return (settings or get_settings()).resolved_default_model()


def _fallback_model(settings: AppSettings | None = None) -> str:
    return (settings or get_settings()).resolved_fallback_model()


class LLMClient:
    """
    Thin wrapper around AsyncOpenAI-compatible clients with:
    - Auto-detection of provider via LLM_PROVIDER env var (azure | openai | ollama)
    - tenacity retry (3 attempts, exponential backoff) on transient errors
    - Per-model failure tracking → auto-switch to fallback_model
    - Per-agent configurable timeout
    """

    def __init__(
        self,
        api_key: str | None = None,        # kept for backward-compat; ignored when provider != openai
        default_model: str | None = None,
        fallback_model: str | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = _build_async_client(self.settings)
        self.default_model = default_model or _default_model(self.settings)
        self.fallback_model = fallback_model or _fallback_model(self.settings)
        self._failure_counts: dict[str, int] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict[str, str] | None = None,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> str:
        use_model = self._resolve_model(model)
        return await self._complete_with_retry(
            messages=messages,
            model=use_model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            timeout=timeout,
            **kwargs,
        )

    async def complete_with_fallback(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Try primary model; if it persistently fails, use fallback directly."""
        try:
            return await self.complete(messages, **kwargs)
        except Exception:
            logger.warning(
                "Primary model failed after retries; using fallback directly",
                fallback=self.fallback_model,
            )
            return await self.complete(messages, model=self.fallback_model, **kwargs)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _resolve_model(self, requested: str | None) -> str:
        model = self.settings.resolve_model_for_provider(requested or self.default_model)
        if self._failure_counts.get(model, 0) >= 3:
            fallback = self.settings.resolve_model_for_provider(self.fallback_model)
            logger.warning(
                "Model has too many failures; switching to fallback",
                primary=model,
                fallback=fallback,
            )
            return fallback
        return model

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _complete_with_retry(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        response_format: dict[str, str] | None,
        timeout: float,
        **kwargs: Any,
    ) -> str:
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if response_format:
            params["response_format"] = response_format

        try:
            response = await self._client.chat.completions.create(**params, **kwargs)
            self._failure_counts[model] = 0  # reset on success
            return response.choices[0].message.content or ""
        except _RETRYABLE as exc:
            self._failure_counts[model] = self._failure_counts.get(model, 0) + 1
            logger.error(
                "LLM call failed",
                model=model,
                error=str(exc),
                failures=self._failure_counts[model],
            )
            raise
