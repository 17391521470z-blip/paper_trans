from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.logging import get_logger


settings = get_settings()
logger = get_logger(__name__)


LLMServiceName = Literal["deepseek", "glm", "openai"]


PRICING_CNY_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.001, 0.002),
    "deepseek-v4-pro": (0.002, 0.008),
    "deepseek-v4-flash": (0.0005, 0.002),
    "deepseek-v4": (0.002, 0.008),
    "deepseek-v3": (0.001, 0.002),
    "deepseek-reasoner": (0.004, 0.016),
    "glm-4-flash": (0.0001, 0.0001),
    "glm-4-air": (0.0001, 0.0001),
    "glm-4": (0.01, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.005, 0.015),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-3.5-turbo": (0.0005, 0.0015),
}


SERVICE_PRICING: dict[LLMServiceName, tuple[float, float]] = {
    "deepseek": (0.001, 0.002),
    "glm": (0.0001, 0.0001),
    "openai": (0.00015, 0.0006),
}


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int = 0

    def __post_init__(self) -> None:
        self.total_tokens = self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class CostBreakdown:
    service: LLMServiceName
    prompt_cost_cny: float
    completion_cost_cny: float
    total_cost_cny: float


@dataclass(slots=True)
class TranslationResult:
    translation: str
    prompt_tokens: int
    completion_tokens: int
    cost_cny: float
    model: str
    raw: dict[str, Any] | None = None


def estimate_tokens(text: str, *, chars_per_token: int = 4) -> int:
    if not text:
        return 0
    return max(1, (len(text) + chars_per_token - 1) // chars_per_token)


def lookup_model_price(model: str) -> tuple[float, float] | None:
    if model in PRICING_CNY_PER_1K_TOKENS:
        return PRICING_CNY_PER_1K_TOKENS[model]
    lower = model.lower()
    for key, price in PRICING_CNY_PER_1K_TOKENS.items():
        if key in lower or lower in key:
            return price
    return None


def compute_cost(
    service: LLMServiceName,
    prompt_tokens: int,
    completion_tokens: int,
    model: str | None = None,
) -> CostBreakdown:
    if model:
        per_model = lookup_model_price(model)
        if per_model:
            prompt_rate, completion_rate = per_model
        else:
            prompt_rate, completion_rate = SERVICE_PRICING.get(
                service, SERVICE_PRICING["deepseek"]
            )
    else:
        prompt_rate, completion_rate = SERVICE_PRICING.get(
            service, SERVICE_PRICING["deepseek"]
        )
    prompt_cost = (prompt_tokens / 1000.0) * prompt_rate
    completion_cost = (completion_tokens / 1000.0) * completion_rate
    return CostBreakdown(
        service=service,
        prompt_cost_cny=round(prompt_cost, 6),
        completion_cost_cny=round(completion_cost, 6),
        total_cost_cny=round(prompt_cost + completion_cost, 6),
    )


def build_glossary_prompt(
    terms: list[dict[str, Any]],
    base_instructions: str | None = None,
) -> str:
    if not terms:
        return base_instructions or ""
    bullet = "\n".join(
        f"- {t.get('term', '')} -> {t.get('translation', '')}"
        + (f" ({t['context']})" if t.get("context") else "")
        for t in terms
        if t.get("term") and t.get("translation")
    )
    parts = [
        base_instructions or "你是一名学术论文翻译助手，请保持术语一致性。",
        "",
        "必须按下列术语对照表翻译（原文 -> 译文）：",
        bullet,
    ]
    return "\n".join(parts)


def build_section_detection_prompt(pages_excerpt: str, max_tokens: int = 1000) -> dict[str, Any]:
    return {
        "task": "detect_sections",
        "max_tokens": max_tokens,
        "input": pages_excerpt,
        "output_schema": {
            "sections": [
                {
                    "name": "string",
                    "start_page": "int",
                    "translate": "bool",
                }
            ]
        },
    }


def get_llm_config(service: LLMServiceName) -> dict[str, str]:
    if service == "deepseek":
        return {
            "api_key": settings.deepseek_api_key,
            "base_url": settings.deepseek_base_url,
            "model": settings.deepseek_model,
        }
    if service == "glm":
        return {
            "api_key": settings.glm_api_key,
            "base_url": settings.glm_base_url,
            "model": settings.glm_model,
        }
    return {
        "api_key": settings.openai_api_key,
        "base_url": settings.openai_base_url,
        "model": settings.openai_model,
    }


class LLMClient(ABC):
    service: LLMServiceName

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict[str, Any]: ...

    async def translate(
        self,
        text: str,
        glossary_prompt: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if glossary_prompt:
            messages.append({"role": "system", "content": glossary_prompt})
        messages.append(
            {
                "role": "user",
                "content": text,
            }
        )
        return await self.chat(messages, model=model)


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        service: LLMServiceName,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        max_retries: int = 3,
    ) -> None:
        cfg = get_llm_config(service)
        self.service = service
        self.api_key = api_key or cfg["api_key"]
        self.base_url = (base_url or cfg["base_url"]).rstrip("/")
        self.default_model = default_model or cfg["model"]
        self.max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError("openai package is required") from exc
            if not self.api_key:
                raise RuntimeError(f"{self.service} api_key not configured")
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        chosen_model = model or self.default_model
        attempts = AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        try:
            async for attempt in attempts:
                with attempt:
                    try:
                        response = await client.chat.completions.create(
                            model=chosen_model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        return self._parse_response(response, chosen_model)
                    except Exception as exc:
                        logger.warning(
                            "llm.retry",
                            service=self.service,
                            model=chosen_model,
                            error=str(exc),
                        )
                        raise
        except RetryError as exc:
            logger.error(
                "llm.failed_after_retries",
                service=self.service,
                model=chosen_model,
                error=str(exc),
            )
            raise

    def _parse_response(self, response: Any, model: str) -> dict[str, Any]:
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
        completion_tokens = int(
            getattr(usage, "completion_tokens", 0) or 0
        ) if usage else 0
        cost = compute_cost(self.service, prompt_tokens, completion_tokens, model=model)
        return {
            "translation": content,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_cny": cost.total_cost_cny,
            "model": model,
            "raw": None,
        }

    async def translate(
        self,
        text: str,
        glossary_prompt: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        return await super().translate(text, glossary_prompt, model=model)


_clients: dict[str, LLMClient] = {}


def get_llm_client(service: LLMServiceName | None = None) -> LLMClient:
    svc = service or settings.llm_default_service
    if svc not in _clients:
        _clients[svc] = OpenAICompatibleClient(svc)
    return _clients[svc]


def reset_llm_clients() -> None:
    _clients.clear()


async def translate_text(
    text: str,
    glossary_prompt: str,
    *,
    service: LLMServiceName | None = None,
    model: str | None = None,
) -> TranslationResult:
    client = get_llm_client(service)
    raw = await client.translate(text, glossary_prompt, model=model)
    return TranslationResult(
        translation=raw["translation"],
        prompt_tokens=raw["prompt_tokens"],
        completion_tokens=raw["completion_tokens"],
        cost_cny=raw["cost_cny"],
        model=raw["model"],
        raw=raw.get("raw"),
    )


async def ainvoke_for_section_detection(
    excerpt: str,
    *,
    service: LLMServiceName | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    client = get_llm_client(service)
    messages = [
        {
            "role": "system",
            "content": (
                "You analyze academic papers and return a JSON list of sections.\n"
                "Each section has: name (string), start_page (int), translate (bool).\n"
                "Mark References / Bibliography / Acknowledgments as translate=false.\n"
                "Respond with valid JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Identify the section structure of the following paper excerpt. "
                "Return JSON only.\n\n" + excerpt[:6000]
            ),
        },
    ]
    return await client.chat(messages, model=model, max_tokens=1000, temperature=0.0)