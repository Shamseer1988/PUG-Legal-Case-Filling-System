"""Structured logging setup via loguru."""

import sys

from loguru import logger

from app.core.config import settings


def setup_logging() -> None:
    logger.remove()
    if settings.log_json:
        logger.add(sys.stdout, level=settings.log_level, serialize=True)
    else:
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
                "<level>{level: <8}</level> "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
            ),
        )
