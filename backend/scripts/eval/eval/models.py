"""论文翻译模型评测：统一调用不同 LLM 并记录成本/耗时/结果."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@dataclass(slots=True)
class ModelResult:
    service: str
    model: str
    block_id: str
    source_text: str
    translation: str
    prompt_tokens: int
    completion_tokens: int
    cost_cny: float
    latency_ms: float
    first_token_ms: float | None = None


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """A model to benchmark. Can be any OpenAI-compatible endpoint.

    Pricing supports either a flat rate or tiered rates:
      - flat:  prompt_price_cny_per_1k / completion_price_cny_per_1k as float
      - tiered: prompt_price_tiers / completion_price_tiers as list of
                {max_tokens: int | None, price: float} ordered from low to high.
    """

    name: str
    base_url: str
    api_key: str
    model: str
    prompt_price_cny_per_1k: float | list[dict[str, Any]] | None = None
    completion_price_cny_per_1k: float | list[dict[str, Any]] | None = None
    prompt_price_tiers: list[dict[str, Any]] | None = None
    completion_price_tiers: list[dict[str, Any]] | None = None
    temperature: float = 0.3
    max_tokens: int | None = 8000
    max_retries: int = 3

    def __post_init__(self) -> None:
        # Normalize legacy flat fields into tier arrays for uniform lookup.
        if self.prompt_price_tiers is None:
            if isinstance(self.prompt_price_cny_per_1k, list):
                object.__setattr__(self, "prompt_price_tiers", self.prompt_price_cny_per_1k)
            elif self.prompt_price_cny_per_1k is not None:
                object.__setattr__(
                    self,
                    "prompt_price_tiers",
                    [{"max_tokens": None, "price": self.prompt_price_cny_per_1k}],
                )
        if self.completion_price_tiers is None:
            if isinstance(self.completion_price_cny_per_1k, list):
                object.__setattr__(
                    self, "completion_price_tiers", self.completion_price_cny_per_1k
                )
            elif self.completion_price_cny_per_1k is not None:
                object.__setattr__(
                    self,
                    "completion_price_tiers",
                    [{"max_tokens": None, "price": self.completion_price_cny_per_1k}],
                )


def _select_tier_price(tiers: list[dict[str, Any]], tokens: int) -> float:
    """Return the price for the first tier whose max_tokens >= tokens."""
    for tier in tiers:
        max_tokens = tier.get("max_tokens")
        if max_tokens is None or tokens <= max_tokens:
            return float(tier["price"])
    # Fallback to the most expensive tier if tokens exceed all explicit limits.
    return float(tiers[-1]["price"])


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    prompt_price: float | list[dict[str, Any]],
    completion_price: float | list[dict[str, Any]],
) -> float:
    prompt_tiers = (
        prompt_price if isinstance(prompt_price, list) else [{"max_tokens": None, "price": prompt_price}]
    )
    completion_tiers = (
        completion_price
        if isinstance(completion_price, list)
        else [{"max_tokens": None, "price": completion_price}]
    )
    prompt_cost = (prompt_tokens / 1000.0) * _select_tier_price(prompt_tiers, prompt_tokens)
    completion_cost = (completion_tokens / 1000.0) * _select_tier_price(
        completion_tiers, completion_tokens
    )
    return round(prompt_cost + completion_cost, 6)


class LLMClient:
    """Thin OpenAI-compatible client for benchmarking."""

    def __init__(self, cfg: ModelConfig) -> None:
        self.cfg = cfg
        self._client = AsyncOpenAI(
            api_key=cfg.api_key,
            base_url=cfg.base_url.rstrip("/"),
        )

    async def translate(
        self,
        source_text: str,
        glossary_prompt: str,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if glossary_prompt:
            messages.append({"role": "system", "content": glossary_prompt})
        messages.append({"role": "user", "content": source_text})

        attempts = AsyncRetrying(
            stop=stop_after_attempt(self.cfg.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        try:
            async for attempt in attempts:
                with attempt:
                    response = await self._client.chat.completions.create(
                        model=self.cfg.model,
                        messages=messages,
                        temperature=self.cfg.temperature,
                        max_tokens=self.cfg.max_tokens,
                    )
                    return self._parse_response(response)
        except RetryError as exc:
            raise RuntimeError(
                f"LLM call failed after retries: {self.cfg.name}/{self.cfg.model}"
            ) from exc

    def _parse_response(self, response: Any) -> dict[str, Any]:
        choices = getattr(response, "choices", None) or []
        content = ""
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            if message is not None:
                content = getattr(message, "content", "") or ""
            elif isinstance(first, dict):
                msg = first.get("message") or {}
                content = msg.get("content", "") if isinstance(msg, dict) else ""

        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        cost = compute_cost(
            prompt_tokens,
            completion_tokens,
            self.cfg.prompt_price_tiers,
            self.cfg.completion_price_tiers,
        )
        return {
            "translation": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_cny": cost,
            "model": getattr(response, "model", self.cfg.model),
        }


async def translate_block(
    block_id: str,
    source_text: str,
    cfg: ModelConfig,
    glossary_prompt: str,
) -> ModelResult:
    client = LLMClient(cfg)
    t0 = time.perf_counter()
    raw = await client.translate(source_text, glossary_prompt)
    latency_ms = (time.perf_counter() - t0) * 1000
    return ModelResult(
        service=cfg.name,
        model=raw["model"],
        block_id=block_id,
        source_text=source_text,
        translation=raw["translation"],
        prompt_tokens=raw["prompt_tokens"],
        completion_tokens=raw["completion_tokens"],
        cost_cny=raw["cost_cny"],
        latency_ms=latency_ms,
    )


async def translate_paper_blocks(
    paper_id: str,
    blocks: list[dict[str, Any]],
    cfg: ModelConfig,
    glossary_prompt: str,
) -> list[ModelResult]:
    """Translate all translatable blocks of one paper for one model."""
    results: list[ModelResult] = []
    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        if not text or not text.strip():
            continue
        block_id = f"{paper_id}::p{block.get('page', 0)}::{block.get('type', 'unknown')}::{idx}"
        result = await translate_block(block_id, text, cfg, glossary_prompt)
        results.append(result)
    return results


def load_model_configs(path: Path) -> list[ModelConfig]:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Allow both { "models": [...] } and plain [...]
    items = data.get("models", data) if isinstance(data, dict) else data
    return [ModelConfig(**item) for item in items]


def save_results(results: list[ModelResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_results(path: Path) -> list[ModelResult]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ModelResult(**item) for item in data]
