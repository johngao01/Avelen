"""Runtime settings helpers.

Keep env access in one place so scrapers/handlers don't duplicate os.getenv logic.
"""

import os


def is_no_send_mode() -> bool:
    """Return True when scrape runs should not dispatch telegram/update latest_time."""
    return os.getenv('SCRAPY_NO_SEND', '0') == '1'


def enable_no_send_mode() -> None:
    """Enable no-send mode for current process and child imports."""
    os.environ['SCRAPY_NO_SEND'] = '1'
