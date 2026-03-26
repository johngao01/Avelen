from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from time import sleep
import requests
from filelock import FileLock

from core.settings import (
    COMMON_HEADERS,
    DEVELOPER_CHAT_ID,
    ERROR_FILE,
    ERROR_NOTIFY_LOCK_FILE,
    ERROR_NOTIFY_STATE_FILE,
    ERROR_TOKEN,
    SEND_LOG_FILE,
    PLATFORM_JSON_ROOTS,
    PLATFORM_MEDIA_ROOTS,
    RATE_LIMIT_STATE,
    TELEGRAM_BASE_URL,
    TELEGRAM_LOCAL_MODE,
)


def get_platform_download_dir(platform: str, username: str) -> str:
    """返回平台媒体文件目录。"""
    return os.path.join(PLATFORM_MEDIA_ROOTS[platform], username)


def get_platform_json_root(platform: str) -> str:
    """返回平台 JSON 根目录。"""
    return PLATFORM_JSON_ROOTS[platform]


def get_platform_json_dir(platform: str, username: str) -> str:
    """返回平台用户 JSON 目录。"""
    return os.path.join(get_platform_json_root(platform), username)


def build_platform_media_path(platform: str, username: str, filename: str) -> str:
    """拼出平台媒体文件完整路径。"""
    return os.path.join(get_platform_download_dir(platform, username), filename)


def build_platform_json_path(platform: str, username: str, filename: str) -> str:
    """拼出平台 JSON 文件完整路径。"""
    return os.path.join(get_platform_json_dir(platform, username), filename)


def read_text_file(path: str | Path, *, encoding: str = 'utf-8') -> str:
    """读取文本文件内容。"""
    with open(path, encoding=encoding) as file_obj:
        return file_obj.read()


def _trim_message(message: str, limit: int = 3800) -> str:
    message = str(message or '').strip()
    if len(message) <= limit:
        return message
    return message[: limit - 3] + '...'


def _build_error_bot_url() -> str:
    if TELEGRAM_LOCAL_MODE:
        return f'{TELEGRAM_BASE_URL}{ERROR_TOKEN}/sendMessage'
    return f'https://api.telegram.org/bot{ERROR_TOKEN}/sendMessage'


def _load_error_notify_state() -> dict[str, dict[str, str]]:
    if not ERROR_NOTIFY_STATE_FILE.exists():
        return {}
    try:
        with open(ERROR_NOTIFY_STATE_FILE, encoding='utf-8') as file_obj:
            data = json.load(file_obj)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_error_notify_state(state: dict[str, dict[str, str]]) -> None:
    with open(ERROR_NOTIFY_STATE_FILE, 'w', encoding='utf-8') as file_obj:
        json.dump(state, file_obj, ensure_ascii=False, indent=2)


def build_error_notify_key(*, category: str, platform: str, userid: str, username: str) -> str:
    return f'{category}:{platform}:{userid}:{username}'


def clear_error_notification(dedupe_key: str, *, logger=None) -> None:
    with FileLock(str(ERROR_NOTIFY_LOCK_FILE), timeout=5):
        state = _load_error_notify_state()
        if dedupe_key in state:
            state.pop(dedupe_key, None)
            _save_error_notify_state(state)
            if logger:
                logger.info(f'已清理错误通知去重状态: {dedupe_key}')


def send_error_notification(message: str, *, logger=None, dedupe_key: str | None = None) -> bool:
    """通过错误通知 Bot 把异常信息推送给开发者。"""
    if not ERROR_TOKEN:
        if logger:
            logger.warning('未配置 ERROR_TELEGRAM_BOT_TOKEN，跳过错误通知')
        return False

    message = _trim_message(message)
    message_hash = hashlib.md5(message.encode('utf-8')).hexdigest()

    try:
        with FileLock(str(ERROR_NOTIFY_LOCK_FILE), timeout=5):
            state = _load_error_notify_state()
            if dedupe_key:
                existing = state.get(dedupe_key) or {}
                if existing.get('message_hash') == message_hash:
                    if logger:
                        logger.info(f'重复错误通知已跳过: {dedupe_key}')
                    return False

            response = requests.post(
                _build_error_bot_url(),
                json={
                    'chat_id': DEVELOPER_CHAT_ID,
                    'text': message,
                },
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get('ok') is False:
                raise RuntimeError(str(payload))

            if dedupe_key:
                state[dedupe_key] = {
                    'message_hash': message_hash,
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
                _save_error_notify_state(state)
            return True
    except Exception as exc:
        if logger:
            logger.warning(f'错误通知发送失败: {exc}')
        return False


def load_netscape_cookies(path: str | Path) -> dict[str, str]:
    """从 Netscape cookies 文件中提取 requests 可用的键值对。"""
    cookies: dict[str, str] = {}
    with open(path, encoding='utf8') as cookie_file:
        for raw_line in cookie_file:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith('#') and not line.startswith('#HttpOnly_'):
                continue
            parts = line.split('\t')
            if len(parts) != 7:
                continue
            cookies[parts[5].strip()] = parts[6].strip()
    return cookies


def build_browser_headers(*,
                          referer: str | None = None,
                          cookie: str | None = None,
                          accept: str | None = None,
                          user_agent: str | None = None,
                          extra: dict[str, str] | None = None) -> dict[str, str]:
    """构建平台共用的浏览器请求头。"""
    headers = {
        'User-Agent': user_agent or COMMON_HEADERS['user_agent'],
        'Accept-Language': COMMON_HEADERS['accept_language'],
    }
    if accept:
        headers['Accept'] = accept
    if referer:
        headers['Referer'] = referer
    if cookie:
        headers['Cookie'] = cookie
    if extra:
        headers.update(extra)
    return headers


def convert_bytes_to_human_readable(num_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f}{unit}"
        num_bytes /= 1024.0


def download_log(response):
    messages = response.get('messages') or []
    if not messages:
        return
    message = messages[-1]
    log = (message['USERNAME'] + " " + message['CREATE_TIME'] + " " + message['DATE_TIME'] +
           " " + message['URL'] + " " + message['TEXT_RAW'].replace('\n', ' '))
    with open(SEND_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log + "\n")


def bytes2md5(r_bytes):
    """
    计算bytes数据的MD5值
    :param r_bytes: 字节行数据，请求下载文件的响应或者打开文件读取到的二进制数据
    :return: MD5值
    """
    file_hash = hashlib.md5()
    file_hash.update(r_bytes)
    return file_hash.hexdigest()


def rate_control(send_result, logger):
    messages = send_result.get('messages') or []
    if not messages:
        return
    RATE_LIMIT_STATE['count'] += len(messages)
    if RATE_LIMIT_STATE['count'] // RATE_LIMIT_STATE['rate'] > RATE_LIMIT_STATE['times']:
        RATE_LIMIT_STATE['times'] += 1
        sleep_time = 60 * (1 + RATE_LIMIT_STATE['times'] / 10)
        logger.info(str(RATE_LIMIT_STATE['count']) + f"  sleep {sleep_time} seconds")
        sleep(sleep_time)


def log_error(url, text=''):
    with open(ERROR_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 处理 {url} 失败  {text}\n")


def find_file_by_name(root_dir, target_filename):
    root_path = Path(root_dir)
    for path in root_path.rglob(target_filename):
        return str(path)  # 找到第一个匹配项后返回
    return None
