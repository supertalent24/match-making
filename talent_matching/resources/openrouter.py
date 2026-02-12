"""OpenRouter LLM resource with automatic cost tracking.

This resource is a thin HTTP client for OpenRouter API. It handles:
- Authentication
- Request formatting
- Cost tracking (stored in PostgreSQL llm_costs table)

LLM operations (prompts and parsing) are in talent_matching.llm.operations.
"""

import asyncio
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from dagster import ConfigurableResource, get_dagster_logger
from pydantic import Field, PrivateAttr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from talent_matching.models.llm_costs import LLMCost


@dataclass
class LLMContext:
    """Context for tracking LLM costs per asset/run."""

    run_id: str = ""
    asset_key: str = ""
    partition_key: str = ""
    code_version: str = ""


class OpenRouterResource(ConfigurableResource):
    """OpenRouter LLM resource with built-in cost tracking.

    This is a thin HTTP client. Use operations from talent_matching.llm for
    specific tasks like CV normalization.

    Example usage in an asset:
        from talent_matching.llm import normalize_cv, CV_PROMPT_VERSION

        openrouter.set_context(
            run_id=context.run_id,
            asset_key="normalized_candidates",
            partition_key=context.partition_key,
            code_version=CV_PROMPT_VERSION,
        )
        result = asyncio.run(normalize_cv(openrouter, cv_text))
    """

    api_key: str = Field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""),
        description="OpenRouter API key",
    )
    default_model: str = Field(
        default="openai/gpt-4o-mini",
        description="Default model to use for completions",
    )
    site_url: str = Field(
        default="https://superteam.fun",
        description="Site URL for OpenRouter analytics",
    )
    app_name: str = Field(
        default="Talent Matching Pipeline",
        description="Application name for OpenRouter analytics",
    )
    # Database connection for cost tracking
    postgres_host: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost"),
    )
    postgres_port: int = Field(
        default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")),
    )
    postgres_user: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_USER", "talent"),
    )
    postgres_password: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "talent_dev"),
    )
    postgres_db: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_DB", "talent_matching"),
    )

    # Internal state (not configurable, uses Pydantic PrivateAttr)
    _context: LLMContext = PrivateAttr(default_factory=LLMContext)

    def set_context(
        self,
        run_id: str,
        asset_key: str,
        partition_key: str = "",
        code_version: str = "",
    ) -> None:
        """Set context for cost tracking. Call this at start of each asset.

        Args:
            run_id: Dagster run ID
            asset_key: Name of the asset being processed
            partition_key: Partition key if applicable
            code_version: Prompt version from the operation module
        """
        self._context = LLMContext(
            run_id=run_id,
            asset_key=asset_key,
            partition_key=partition_key,
            code_version=code_version,
        )

    def _get_db_url(self) -> str:
        """Build PostgreSQL connection URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    async def _store_cost_record(
        self,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
    ) -> None:
        """Store cost record in PostgreSQL.

        Uses a sync database operation wrapped in asyncio.to_thread to avoid
        blocking the event loop.
        """

        def _insert_record() -> None:
            engine = create_engine(self._get_db_url())
            with Session(engine) as session:
                cost_record = LLMCost(
                    run_id=self._context.run_id or "unknown",
                    asset_key=self._context.asset_key or "unknown",
                    partition_key=self._context.partition_key or None,
                    operation=operation,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    code_version=self._context.code_version or None,
                )
                session.add(cost_record)
                session.commit()

        await asyncio.to_thread(_insert_record)

    def _log_cost(
        self,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
    ) -> None:
        """Log cost to Dagster logger."""
        logger = get_dagster_logger()
        logger.info(
            f"LLM Cost: {operation} | {model} | "
            f"{input_tokens}+{output_tokens} tokens | ${cost_usd:.6f}"
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        operation: str = "completion",
        response_format: dict[str, str] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Make an async completion request and track costs.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to default_model)
            operation: Operation type for cost tracking
            response_format: Response format (e.g., {"type": "json_object"})
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens in response

        Returns:
            Full API response dict including usage information
        """
        model = model or self.default_model

        request_body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if response_format:
            request_body["response_format"] = response_format

        if max_tokens:
            request_body["max_tokens"] = max_tokens

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.app_name,
                },
                json=request_body,
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        # Extract usage from response (always included by OpenRouter)
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        # OpenRouter returns cost directly - no need to calculate
        cost_usd = Decimal(str(usage.get("cost", 0)))

        # Log to Dagster
        self._log_cost(operation, model, input_tokens, output_tokens, cost_usd)

        # Store in database
        await self._store_cost_record(
            operation=operation,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        return data
