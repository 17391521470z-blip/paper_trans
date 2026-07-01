"""线上 A/B 测试：根据用户 ID 分配模型."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from app.core.config import get_settings


LLMServiceName = Literal["deepseek", "glm", "openai"]


@dataclass(frozen=True, slots=True)
class ABTestModel:
    service: LLMServiceName
    model: str | None
    label: str  # internal label for experiment tracking


# Example: 3-way equal split. Adjust weights based on traffic and risk appetite.
AB_TEST_VARIANTS: list[ABTestModel] = [
    ABTestModel("deepseek", None, "control_deepseek"),
    ABTestModel("glm", None, "test_glm"),
    ABTestModel("openai", None, "test_openai"),
]


def assign_model_by_user_id(user_id: str) -> ABTestModel:
    """Deterministically assign a model variant to a user.

    Uses a hash so that the same user always gets the same variant within
    an experiment, keeping per-user experience consistent.
    """
    digest = hashlib.sha256(user_id.encode()).hexdigest()
    bucket = int(digest[:8], 16) % len(AB_TEST_VARIANTS)
    return AB_TEST_VARIANTS[bucket]


def resolve_model_for_user(user_id: str) -> tuple[LLMServiceName, str | None]:
    """Return the (service, model) to use for a given user.

    Falls back to settings default if A/B test is disabled.
    """
    settings = get_settings()
    # Flip this to False to disable A/B and use default for everyone.
    ab_test_enabled = False
    if not ab_test_enabled:
        return settings.llm_default_service, None

    variant = assign_model_by_user_id(str(user_id))
    return variant.service, variant.model
