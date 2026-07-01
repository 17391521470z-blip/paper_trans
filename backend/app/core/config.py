from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    app_version: str = "0.1.0"
    app_name: str = "paper-translate"

    database_url: str = Field(
        default="sqlite+aiosqlite:///./paper_translate.db",
        description="SQLAlchemy async database URL",
    )
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20

    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    jwt_issuer: str = "paper-translate"

    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_region: str = ""
    oss_signed_url_expire: int = 86400
    oss_lifecycle_days: int = 1

    llm_default_service: Literal["deepseek", "glm", "openai"] = "deepseek"
    llm_max_tokens_per_call: int = 8000
    llm_daily_cost_limit_cny: float = 50.0
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-4-flash"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    wechat_app_id: str = ""
    wechat_mch_id: str = ""
    wechat_api_key: str = ""
    wechat_notify_url: str = ""
    wechat_pay_enabled: bool = False

    alipay_app_id: str = ""
    alipay_private_key_path: str = ""
    alipay_public_key_path: str = ""
    alipay_notify_url: str = ""
    alipay_enabled: bool = False

    sms_provider: Literal["aliyun", "tencent", "mock"] = "mock"
    sms_access_key_id: str = ""
    sms_access_key_secret: str = ""
    sms_sign_name: str = "PaperTranslate"
    sms_template_code: str = ""
    sms_code_expire_seconds: int = 300

    upload_max_size: int = 52428800
    upload_max_pages: int = 100
    upload_tmp_dir: str = "./tmp/paper-translate/uploads"

    # HIDDEN-FEATURE: md/docx 导出开关(默认关闭)
    # 详见 HIDDEN_FEATURES.md
    enable_markdown_export: bool = False
    enable_docx_export: bool = False

    allowed_origins: str = "http://localhost,http://localhost:5173"
    allowed_origins_list: list[str] = Field(default_factory=list)

    sentry_dsn: str = ""
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.1

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    wecom_webhook_url: str = ""
    wecom_webhook_mentioned_mobile: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Paper Translate"

    verify_code_expire_seconds: int = 300
    verify_code_length: int = 6
    verify_code_dev_value: str = "123456"

    @field_validator("allowed_origins_list", mode="before")
    @classmethod
    def _split_origins(cls, _value: object) -> list[str]:
        return []

    @field_validator("database_url")
    @classmethod
    def _ensure_async_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("sqlite://") and "+aiosqlite" not in value:
            return value.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return value

    def model_post_init(self, __context: object) -> None:
        raw = self.allowed_origins or ""
        self.allowed_origins_list = [
            origin.strip() for origin in raw.split(",") if origin.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
