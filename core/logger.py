from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger as _logger

_STDERR_CONFIGURED = False
_FILE_SINK_KEYS: set[tuple[str, str]] = set()


def get_platform_logger(platform_name: str, log_dir: Path, *, file_level: str = 'INFO'):
    """返回平台专用 logger，并确保公共 sink 只注册一次。"""
    global _STDERR_CONFIGURED

    log_dir.mkdir(exist_ok=True)
    logger_name = f'scrapy_{platform_name}'

    if not _STDERR_CONFIGURED:
        _logger.remove()
        _logger.add(
            sys.stderr,
            format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
            level='INFO',
        )
        _STDERR_CONFIGURED = True

    sink_key = (platform_name, str(log_dir.resolve()))
    if sink_key not in _FILE_SINK_KEYS:
        _logger.add(
            str(log_dir / f'scrapy_{platform_name}.log'),
            format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
            level=file_level,
            encoding='utf-8',
            filter=lambda record, current_name=logger_name: record['extra'].get('name') == current_name,
        )
        _FILE_SINK_KEYS.add(sink_key)

    return _logger.bind(name=logger_name)
