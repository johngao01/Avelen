"""
统一发送分发器：
1) 直接在本地进程内发送 Telegram（不依赖 webhook Flask）
2) 串行化发送，避免多爬虫并发发送导致消息交错
3) 发送媒体后立即入库，再发送文本再入库
"""

import asyncio
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
from core.models import DownloadedFile, PostData
from core.settings import TELEGRAM_BASE_FILE_URL, TELEGRAM_BASE_URL, TELEGRAM_LOCAL_MODE
from filelock import FileLock

DEVELOPER_CHAT_ID = 708424141
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
MARKDOWN_CHAR = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
LOCK_FILE = "telegram_sender.lock"


def _build_bot() -> Bot:
    """构造 Telegram Bot 实例。

    - 默认启用本地模式，连接本地 Bot API Server
    - 当 `TELEGRAM_LOCAL_MODE=0` 时，退回官方默认模式 `Bot(token=TOKEN)`
    """
    if not TOKEN:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is required')
    if TELEGRAM_LOCAL_MODE:
        return Bot(
            token=TOKEN,
            local_mode=True,
            base_url=TELEGRAM_BASE_URL,
            base_file_url=TELEGRAM_BASE_FILE_URL,
        )
    return Bot(token=TOKEN)


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
        print('Get TimeoutError')
    except telegram.error.BadRequest:
        print('Get BadRequest Error')
    except telegram.error.RetryAfter as e:
        if 'Flood control exceeded. Retry in' in e.message:
            second = int(e.message.split(' ')[-2])
            await asyncio.sleep(second)
        print('Get RetryAfter Error')
    return None


def process_message(message: telegram.Message, data: PostData):
    username = data.display_username
    return {
        'MESSAGE_ID': message.message_id,
        'CAPTION': message.caption or '',
        'CHAT_ID': message.chat_id or '',
        'DATE_TIME': datetime.strftime(message.date, '%Y-%m-%d %H:%M:%S'),
        'FORM_USER': message.from_user.id,
        'CHAT': message.chat.id,
        'MEDIA_GROUP_ID': message.media_group_id or '',
        'TEXT_RAW': data.text_raw,
        'URL': data.url,
        'USERID': data.userid,
        'USERNAME': username,
        'CREATE_TIME': data.create_time,
        'IDSTR': data.idstr,
        'MBLOGID': data.mblogid,
        'MSG_STR': message.to_json(),
    }


def persist_messages(messages: telegram.Message | list[telegram.Message] | None, data: PostData) -> list[
    dict[str, Any]]:
    """将 Telegram 返回消息结构落库。"""
    if isinstance(messages, telegram.Message):
        messages = [messages]
    persisted_rows: list[dict[str, Any]] = []
    conn = get_db_conn()
    try:
        for m in messages:
            send_response_dict = process_message(m, data)
            insert_data(conn, 'messages', MESSAGES, send_response_dict)
            persisted_rows.append(send_response_dict)
    finally:
        conn.close()
    return persisted_rows


def rearrange_files(file_list: list[DownloadedFile]) -> list[list[DownloadedFile]]:
    """将文件切分为符合 Telegram 限制的相册组 (单组最多10个，总大小<=50MB)"""
    result_lists = []
    current_list: list[DownloadedFile] = []
    current_size = 0
    for file in file_list:
        size = file.size
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


async def process_and_send_media(
        tg_bot,
        filetype,
        media_list: list[DownloadedFile],
        data: PostData,
        persisted_messages: list[dict[str, Any]],
):
    """处理同类型媒体并在发送后立即落库。"""
    if not media_list:
        return

    # 情况1: 单个文件
    if len(media_list) == 1:
        file = media_list[0]
        path = file.path
        caption = file.caption
        ext = file.ext

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

        persisted_messages.extend(persist_messages(res, data))

    # 情况2: 多个文件 (Album)
    else:
        albums = rearrange_files(media_list)
        for album in albums:
            medias = []
            open_files = []  # 追踪已打开的文件指针，保证最终全部关闭
            try:
                for file in album:
                    path = file.path
                    caption = file.caption or os.path.basename(path)
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

                persisted_messages.extend(persist_messages(res_msgs, data))

            finally:
                # 确保清理释放所有打开的文件资源
                for f in open_files:
                    f.close()


async def execute_task(data: PostData):
    tg_bot = _build_bot()
    raw_files = data.files
    photos, videos, documents = [], [], []

    for file in raw_files:
        filetype = file.filetype
        if filetype == 'video':
            videos.append(file)
        elif filetype == 'photo':
            photos.append(file)
        else:
            documents.append(file)

    persisted_messages: list[dict[str, Any]] = []

    # 按类别分批发送媒体 (图片 -> 视频 -> 文档)
    await process_and_send_media(tg_bot, 'photo', photos, data, persisted_messages)
    await process_and_send_media(tg_bot, 'video', videos, data, persisted_messages)
    await process_and_send_media(tg_bot, 'document', documents, data, persisted_messages)

    # 最后发送总结/文字信息
    raw_msg = data.text_raw or ''
    id_str = replace_char(data.idstr or '')
    cleared_name = clear_name(data.display_username)
    escaped_msg = replace_char(raw_msg)

    text = f"\\#{cleared_name}  [{id_str}]({data.url})\n\n{escaped_msg}"

    send_response = await retry_send(
        tg_bot.sendMessage,
        chat_id=DEVELOPER_CHAT_ID,
        text=text,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    if not send_response:
        raise Exception("最终文本消息发送失败")

    persisted_messages.extend(persist_messages(send_response, data))

    return persisted_messages


def send_post_payload_to_telegram(data: PostData):
    """发送标准化 payload 到 Telegram，并返回统一结果字典。

    入参 `data` 是平台层整理好的标准化 payload，常见字段包括：
    - `username` / `nickname`
    - `url` / `userid` / `idstr` / `mblogid`
    - `create_time` / `text_raw`
    - `files`: 下载层返回的 `DownloadedFile` 列表

    返回值始终是 `dict`，核心字段如下：
    - `ok`: 发送是否成功
    - `error`: 失败原因，成功时为 `None`
    - `messages`: 已落库的消息记录列表
    """
    lock = FileLock(LOCK_FILE, timeout=3600)
    with lock:
        try:
            persisted_messages = asyncio.run(execute_task(data))
            return {
                'ok': True,
                'error': None,
                'post_data': data,
                'messages': persisted_messages,
            }
        except Exception as e:
            traceback.print_exc()
            return {
                'ok': False,
                'error': str(e),
                'post_data': data,
                'messages': [],
            }
