"""Shared scraper pipeline helpers.

This module centralizes send-result handling and side effects (rate control, update_db)
so each platform scraper focuses on crawl/parse logic.
"""

from typing import Callable

from tools.settings import is_no_send_mode
from tools.utils import download_log, rate_control


def is_send_success(result) -> bool:
    return getattr(result, 'status_code', None) == 200


def handle_success(result, logger, on_update: Callable[[], None] | None = None):
    """Handle standard success side effects for one dispatched post."""
    if not is_no_send_mode():
        download_log(result)
        rate_control(result, logger)
        if on_update:
            on_update()


def update_after_batch(on_update: Callable[[], None] | None = None):
    """Run end-of-batch user latest_time update when send mode is enabled."""
    if not is_no_send_mode() and on_update:
        on_update()
