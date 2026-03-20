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


def is_download_progress_enabled() -> bool:
    """Return True when download progress bars should be shown."""
    return os.getenv('SCRAPY_DOWNLOAD_PROGRESS', '1') == '1'


def enable_download_progress() -> None:
    """Enable download progress bars for current process and child imports."""
    os.environ['SCRAPY_DOWNLOAD_PROGRESS'] = '1'


def disable_download_progress() -> None:
    """Disable download progress bars for current process and child imports."""
    os.environ['SCRAPY_DOWNLOAD_PROGRESS'] = '0'


