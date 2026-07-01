import logging
import sys
from typing import Any

import structlog


def configure_logging(level: str, environment: str) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _add_environment_processor(environment),
    ]

    if environment in {"development", "test"}:
        renderer: Any = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(log_level)


def _add_environment_processor(environment: str):
    def _processor(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict.setdefault("env", environment)
        return event_dict

    return _processor


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
