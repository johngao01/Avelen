from __future__ import annotations
import hashlib
import os
from datetime import datetime
from pathlib import Path
from time import sleep

from core.settings import (
    COMMON_HEADERS,
    ERROR_FILE,
    SEND_LOG_FILE,
    MAX_DOCUMENT_SIZE,
    MAX_PHOTO_SIZE,
    MAX_PHOTO_TOTAL_PIXEL,
    MAX_VIDEO_SIZE,
    PLATFORM_JSON_ROOTS,
    PLATFORM_MEDIA_ROOTS,
    RATE_LIMIT_STATE,
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


def handler_file(save_path, index, logger):
    from PIL import Image
    media_name = os.path.basename(save_path)
    size = os.path.getsize(save_path)
    file_type = media_name.split('.')[-1]
    human_readable_size = convert_bytes_to_human_readable(size)
    file_data = {
        'media': save_path,
        'caption': media_name,
        'size': size
    }
    if file_type in ['jpg', 'png', 'jpeg']:
        img = Image.open(save_path)
        msg = ' '.join(["\t", str(index), save_path, str(img.width) + "*" + str(img.height), human_readable_size])
        logger.info(msg)
        if img.width + img.height > MAX_PHOTO_TOTAL_PIXEL:
            if size < MAX_DOCUMENT_SIZE:
                file_data.update({'type': 'document'})
            else:
                return None
        else:
            if size < MAX_PHOTO_SIZE:
                file_data.update({'type': 'photo'})
            elif MAX_PHOTO_SIZE < size < MAX_DOCUMENT_SIZE:
                file_data.update({'type': 'document'})
            else:
                return None
        return file_data
    else:
        if size < MAX_VIDEO_SIZE:
            file_data.update({'type': 'video'})
        else:
            return None
        return file_data
