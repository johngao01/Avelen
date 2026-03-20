"""Global settings and runtime flags.

职责划分：
- 这个模块只负责“配置”和“运行时开关”
- `platforms.toml` 在模块导入时只读取一次
- 其他模块直接导入这里暴露的常量，不再重复套一层配置 helper
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / 'config' / 'platforms.toml'
COOKIES_DIR = PROJECT_ROOT / 'cookies'
LOGS_DIR = PROJECT_ROOT / 'logs'
ERROR_FILE = LOGS_DIR / 'error.txt'
SEND_LOG_FILE = LOGS_DIR / 'send.log'
LOGS_DIR.mkdir(exist_ok=True)
MAX_PHOTO_SIZE = 10 * 1024 * 1024
MAX_PHOTO_TOTAL_PIXEL = 7000
MAX_VIDEO_SIZE = 500 * 1024 * 1024
MAX_DOCUMENT_SIZE = 500 * 1024 * 1024
ERROR_TOKEN = os.getenv('ERROR_TELEGRAM_BOT_TOKEN', '')
DEVELOPER_CHAT_ID = 708424141
SCRAPY_FAVORITE_LIMIT = 100
RATE_LIMIT_STATE = {
    'count': 0,
    'times': 0,
    'rate': 60,
}

with open(CONFIG_PATH, 'rb') as file_obj:
    PLATFORM_SETTINGS = tomllib.load(file_obj)
COMMON_HEADERS = dict(PLATFORM_SETTINGS['headers']['common'])
PLATFORM_CONFIGS = {
    name: dict(config)
    for name, config in PLATFORM_SETTINGS['platforms'].items()
}
DOWNLOAD_ROOT = os.getenv('DOWNLOAD_ROOT', PLATFORM_SETTINGS['paths']['download_root'])

PLATFORM_JSON_ROOTS = {
    platform: os.path.join(DOWNLOAD_ROOT, platform, 'json')
    for platform in PLATFORM_CONFIGS
}
PLATFORM_MEDIA_ROOTS = {
    platform: os.path.join(DOWNLOAD_ROOT, platform)
    for platform in PLATFORM_CONFIGS
}

WEIBO_CONFIG = PLATFORM_CONFIGS['weibo']
DOUYIN_CONFIG = PLATFORM_CONFIGS['douyin']
BILIBILI_CONFIG = PLATFORM_CONFIGS['bilibili']
INSTAGRAM_CONFIG = PLATFORM_CONFIGS['instagram']

WEIBO_JSON_ROOT = PLATFORM_JSON_ROOTS['weibo']
DOUYIN_JSON_ROOT = PLATFORM_JSON_ROOTS['douyin']
BILIBILI_JSON_ROOT = PLATFORM_JSON_ROOTS['bilibili']
INSTAGRAM_JSON_ROOT = PLATFORM_JSON_ROOTS['instagram']

WEIBO_COOKIE_PATH = COOKIES_DIR / WEIBO_CONFIG['cookie_file']
DOUYIN_COOKIE_PATH = COOKIES_DIR / DOUYIN_CONFIG['cookie_file']
DOUYIN_FAVORITE_COOKIE_PATH = COOKIES_DIR / DOUYIN_CONFIG['favorite_cookie_file']
BILIBILI_COOKIE_PATH = COOKIES_DIR / BILIBILI_CONFIG['cookie_file']
INSTAGRAM_COOKIE_PATH = COOKIES_DIR / INSTAGRAM_CONFIG['cookie_file']


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
