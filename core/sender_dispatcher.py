"""
统一发送分发器：
1) 直接在本地进程内发送 Telegram（不依赖 webhook Flask）
2) 串行化发送，避免多爬虫并发发送导致消息交错
3) 发送媒体后立即入库，再发送文本再入库
"""

import asyncio
import json
import os
import re
import traceback
from datetime import datetime
from typing import Any
import emoji
import telegram
from telegram import Bot, InputMediaDocument, InputMediaPhoto, InputMediaVideo
from telegram.constants import ChatAction, ParseMode

from core.database import insert_data, get_db_conn, MESSAGES
from filelock import FileLock

DEVELOPER_CHAT_ID = 708424141
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
API_URL = 'http://localhost:8081/bot'
FILE_API_URL = 'http://localhost:8081/file/bot'
MARKDOWN_CHAR = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
LOCK_FILE = "telegram_sender.lock"


def _build_bot() -> Bot:
    if not TOKEN:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is required')
    return Bot(token=TOKEN, local_mode=True, base_url=API_URL, base_file_url=FILE_API_URL)


def clear_name(text):
    result = re.sub(r'[（(【].*?[】)）]', '', text)
    result = emoji.demojize(result)
    result = re.sub(r':\S+?:', '', result)
    result = re.sub(r'[^\w]', '', result)
    result = result.replace('_', '\\_')
    return result or '没有名字'


def replace_char(text):
    for char in MARKDOWN_CHAR:
        text = text.replace(char, f'\\{char}')
    return text


async def retry_send(fun, **kwargs):
    try:
        return await fun(**kwargs, read_timeout=42, write_timeout=40, connect_timeout=40, pool_timeout=40)
    except telegram.error.TimedOut:
        print('Get TimeoutError:\n' + traceback.format_exc())
    except telegram.error.BadRequest:
        print('Get BadRequest Error:\n' + traceback.format_exc())
    except telegram.error.RetryAfter as e:
        if 'Flood control exceeded. Retry in' in e.message:
            second = int(e.message.split(' ')[-2])
            await asyncio.sleep(second)
        print('Get RetryAfter Error:\n' + traceback.format_exc())
    return None


def ensure_message_list(messages: telegram.Message | list[telegram.Message] | None) -> list[telegram.Message]:
    if not messages:
        return []
    if isinstance(messages, list):
        return messages
    return [messages]


def serialize_telegram_message(message: telegram.Message) -> dict[str, Any]:
    try:
        return json.loads(message.to_json())
    except Exception:
        return {
            'message_id': getattr(message, 'message_id', None),
            'chat_id': getattr(message, 'chat_id', None),
            'date': datetime.strftime(message.date, '%Y-%m-%d %H:%M:%S') if getattr(message, 'date', None) else None,
            'caption': getattr(message, 'caption', None),
            'text': getattr(message, 'text', None),
        }


def process_message(message: telegram.Message, data):
    username = data['nickname'] if data.get('username') == 'favorite' and 'nickname' in data else data['username']
    item = {
        'MESSAGE_ID': message.message_id,
        'CAPTION': message.caption or '',
        'CHAT_ID': message.chat_id or '',
        'DATE_TIME': datetime.strftime(message.date, '%Y-%m-%d %H:%M:%S'),
        'FORM_USER': message.from_user.id,
        'CHAT': message.chat.id,
        'MEDIA_GROUP_ID': message.media_group_id or '',
        'TEXT_RAW': data['text_raw'],
        'URL': data['url'],
        'USERID': data['userid'],
        'USERNAME': username,
        'CREATE_TIME': data['create_time'],
        'IDSTR': data['idstr'],
        'MBLOGID': data['mblogid'],
        'MSG_STR': message.to_json(),
        'PHOTO': {},
        'VIDEO': {},
        'DOCUMENT': {}
    }
    return item


def persist_messages(messages: telegram.Message | list[telegram.Message] | None, data) -> list[dict[str, Any]]:
    """将 telegram 返回消息结构落库（messages/video/photo/document）。"""
    normalized_messages = ensure_message_list(messages)
    if not normalized_messages:
        return []
    persisted_rows: list[dict[str, Any]] = []
    conn = get_db_conn()
    try:
        for m in normalized_messages:
            send_response_dict = process_message(m, data)
            insert_data(conn, 'messages', MESSAGES, send_response_dict)
            persisted_rows.append(send_response_dict)
    finally:
        conn.close()
    return persisted_rows


def append_send_event(processed_results: list[dict[str, Any]],
                      *,
                      event_type: str,
                      filetype: str,
                      request_items: list[dict[str, Any]],
                      telegram_messages: telegram.Message | list[telegram.Message] | None,
                      persisted_messages: list[dict[str, Any]],
                      extra: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_messages = ensure_message_list(telegram_messages)
    event = {
        'event_type': event_type,
        'filetype': filetype,
        'request_items': request_items,
        'message_count': len(normalized_messages),
        'messages': [serialize_telegram_message(message) for message in normalized_messages],
        'persisted_messages': persisted_messages,
    }
    if extra:
        event.update(extra)
    processed_results.append(event)
    return event


def rearrange_files(file_list):
    """将文件切分为符合 Telegram 限制的相册组 (单组最多10个，总大小<=50MB)"""
    result_lists = []
    current_list = []
    current_size = 0
    for file in file_list:
        size = file[-1]
        if len(current_list) < 10 and current_size + size <= 50 * 1024 * 1024:
            current_list.append(file)
            current_size += size
        else:
            if current_list:
                result_lists.append(current_list)
            current_list = [file]
            current_size = size
    if current_list:
        result_lists.append(current_list)
    return result_lists


async def process_and_send_media(tg_bot, filetype, media_list, data, processed_results):
    """合并处理单文件和多文件的发送，并即时提取信息"""
    if not media_list:
        return

    # 情况1: 单个文件
    if len(media_list) == 1:
        path, caption, size = media_list[0]
        ext = os.path.splitext(path)[1][1:].lower()

        with open(path, 'rb') as f:
            if filetype == 'document':
                await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_DOCUMENT)
                res = await retry_send(tg_bot.send_document, chat_id=DEVELOPER_CHAT_ID, document=f, caption=caption)
            elif filetype == 'video' or ext in ['mp4', 'mov', 'gif']:
                await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_VIDEO)
                res = await retry_send(tg_bot.send_video, chat_id=DEVELOPER_CHAT_ID, video=f, caption=caption)
            else:
                await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_PHOTO)
                res = await retry_send(tg_bot.send_photo, chat_id=DEVELOPER_CHAT_ID, photo=f, caption=caption)

        if not res:
            raise Exception(f"发送单个文件失败: {path}")

        persisted_rows = persist_messages(res, data)
        append_send_event(
            processed_results,
            event_type='media_single',
            filetype=filetype,
            request_items=[{
                'path': path,
                'caption': caption,
                'size': size,
            }],
            telegram_messages=res,
            persisted_messages=persisted_rows,
        )

    # 情况2: 多个文件 (Album)
    else:
        albums = rearrange_files(media_list)
        for album in albums:
            medias = []
            open_files = []  # 追踪已打开的文件指针，保证最终全部关闭
            try:
                for path, caption, size in album:
                    f = open(path, 'rb')
                    open_files.append(f)
                    if filetype == 'video':
                        medias.append(InputMediaVideo(f, caption=caption))
                    elif filetype == 'photo':
                        medias.append(InputMediaPhoto(f, caption=caption))
                    else:
                        medias.append(InputMediaDocument(f, caption=caption))

                # 发送前动作提示
                if filetype == 'video':
                    await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_VIDEO)
                elif filetype == 'photo':
                    await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_PHOTO)
                else:
                    await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_DOCUMENT)

                # 发送媒体组
                res_msgs = await retry_send(tg_bot.send_media_group, chat_id=DEVELOPER_CHAT_ID, media=medias)

                if not res_msgs:
                    raise Exception(f"发送相册失败，包含文件数: {len(medias)}")

                persisted_rows = persist_messages(res_msgs, data)
                append_send_event(
                    processed_results,
                    event_type='media_group',
                    filetype=filetype,
                    request_items=[{
                        'path': path,
                        'caption': caption,
                        'size': size,
                    } for path, caption, size in album],
                    telegram_messages=res_msgs,
                    persisted_messages=persisted_rows,
                    extra={'album_size': len(album)},
                )

            finally:
                # 确保清理释放所有打开的文件资源
                for f in open_files:
                    f.close()


async def execute_task(data):
    tg_bot = _build_bot()
    processed_results = []

    # 解析文件列表
    raw_files = data.get('files')
    if isinstance(raw_files, dict):
        raw_files = [raw_files]  # 将字典强转为列表统一处理
    elif not raw_files:
        raw_files = []

    photos, videos, documents = [], [], []

    for file in raw_files:
        path = file.get('path') or file.get('media', '')
        caption = file.get('caption') or os.path.basename(path)
        size = file.get('size') or os.path.getsize(path)
        filetype = file.get('type')

        if filetype == 'video':
            videos.append([path, caption, size])
        elif filetype == 'photo':
            photos.append([path, caption, size])
        else:
            documents.append([path, caption, size])

    # 按类别分批发送媒体 (图片 -> 视频 -> 文档)
    await process_and_send_media(tg_bot, 'photo', photos, data, processed_results)
    await process_and_send_media(tg_bot, 'video', videos, data, processed_results)
    await process_and_send_media(tg_bot, 'document', documents, data, processed_results)

    # 最后发送总结/文字信息
    raw_msg = data.get('text_raw', '')
    if raw_msg or data.get('url'):
        id_str = replace_char(data.get('idstr', ''))
        if data['username'] == 'favorite' and 'nickname' in data:
            username = data['nickname']
        else:
            username = data['username']
        cleared_name = clear_name(username)
        escaped_msg = replace_char(raw_msg)

        text = f"\\#{cleared_name}  [{id_str}]({data.get('url', '')})\n\n{escaped_msg}"

        send_response = await retry_send(
            tg_bot.sendMessage,
            chat_id=DEVELOPER_CHAT_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        if not send_response:
            raise Exception("最终文本消息发送失败")

        persisted_rows = persist_messages(send_response, data)
        append_send_event(
            processed_results,
            event_type='text',
            filetype='text',
            request_items=[{
                'text': text,
                'raw_text': raw_msg,
                'url': data.get('url', ''),
            }],
            telegram_messages=send_response,
            persisted_messages=persisted_rows,
            extra={'parse_mode': 'MARKDOWN_V2'},
        )
    telegram_messages = [
        message
        for event in processed_results
        for message in event['messages']
    ]
    persisted_messages = [
        message
        for event in processed_results
        for message in event['persisted_messages']
    ]
    return {
        'chat_id': DEVELOPER_CHAT_ID,
        'event_count': len(processed_results),
        'message_count': len(telegram_messages),
        'events': processed_results,
        'messages': telegram_messages,
        'persisted_messages': persisted_messages,
    }


def send_post_payload_to_telegram(data: dict):
    """发送标准化 payload 到 Telegram，并返回统一结果字典。

    入参 `data` 是平台层整理好的标准化 payload，常见字段包括：
    - `username` / `nickname`
    - `url` / `userid` / `idstr` / `mblogid`
    - `create_time` / `text_raw`
    - `files`: 单个文件字典或文件字典列表

    返回值始终是 `dict`，核心字段如下：
    - `ok`: 发送是否成功
    - `error`: 失败原因，成功时为 `None`
    - `persisted`: 是否已写入 `messages` 表
    - `messages`: 已落库的消息记录列表
    - `telegram`: 发送过程详情

    其中 `telegram` 还包含：
    - `chat_id`: 发送目标 chat
    - `event_count`: 发送步骤数量
    - `message_count`: Telegram 实际返回的消息数量
    - `events`: 每一步的详细发送事件
    - `messages`: Telegram 原始消息 JSON 列表
    - `persisted_messages`: 与数据库落库对应的消息记录
    """
    lock = FileLock(LOCK_FILE, timeout=3600)
    with lock:
        try:
            telegram_result = asyncio.run(execute_task(data))
            return {
                'ok': True,
                'error': None,
                'persisted': True,
                'messages': telegram_result['persisted_messages'],
                'telegram': telegram_result,
            }
        except Exception as e:
            traceback.print_exc()
            return {
                'ok': False,
                'error': str(e),
                'persisted': False,
                'messages': [],
                'telegram': {
                    'chat_id': DEVELOPER_CHAT_ID,
                    'event_count': 0,
                    'message_count': 0,
                    'events': [],
                    'messages': [],
                    'persisted_messages': [],
                },
            }
