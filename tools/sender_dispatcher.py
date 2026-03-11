import asyncio
import os
import re
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime

import emoji
import telegram
from telegram import Bot, InputMediaDocument, InputMediaPhoto, InputMediaVideo
from telegram.constants import ChatAction, ParseMode

from tools.database import insert_data, get_db_conn, MESSAGES, PHOTO, VIDEO, DOCUMENT

try:
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None

DEVELOPER_CHAT_ID = 708424141
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
API_URL = 'http://localhost:8081/bot'
FILE_API_URL = 'http://localhost:8081/file/bot'
MARKDOWN_CHAR = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
SEND_LOCK = threading.Lock()
LOCK_FILE = '/tmp/weibo_tg_sender.lock'


@dataclass
class LocalResponse:
    status_code: int
    payload: dict

    def json(self):
        return self.payload


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
    if message.video:
        item['VIDEO'] = {
            'file_id': message.video.file_id,
            'file_unique_id': message.video.file_unique_id,
            'height': message.video.height,
            'width': message.video.width,
            'duration': message.video.duration or 0,
            'file_name': message.video.file_name,
            'file_size': message.video.file_size or 0,
            'file_type': message.video.mime_type or 'mp4',
            'message_id': message.message_id,
            'media_group_id': message.media_group_id,
            'url': data['url'],
        }
    if message.photo:
        for p in message.photo:
            item['PHOTO'][p.file_id] = {
                'file_id': p.file_id,
                'file_unique_id': p.file_unique_id,
                'width': p.width,
                'height': p.height,
                'file_size': p.file_size or 0,
                'file_name': item['CAPTION'],
                'message_id': message.message_id,
                'media_group_id': message.media_group_id,
                'url': data['url'],
            }
    if message.document:
        item['DOCUMENT'] = {
            'file_id': message.document.file_id,
            'file_unique_id': message.document.file_unique_id,
            'file_name': message.document.file_name,
            'file_type': message.document.mime_type or '',
            'file_size': message.document.file_size or 0,
            'message_id': message.message_id,
            'media_group_id': message.media_group_id,
            'url': data['url'],
        }
    return item


def persist_messages(messages):
    if not messages:
        return
    conn = get_db_conn()
    try:
        for m in messages:
            insert_data(conn, 'messages', MESSAGES, m)
            if m['VIDEO']:
                insert_data(conn, 'video', VIDEO, m['VIDEO'])
            if m['PHOTO']:
                for _, v in m['PHOTO'].items():
                    insert_data(conn, 'photo', PHOTO, v)
            if m['DOCUMENT']:
                insert_data(conn, 'document', DOCUMENT, m['DOCUMENT'])
    finally:
        conn.close()


async def _send_media_and_text(data):
    bot = _build_bot()
    files = data.get('files')
    if isinstance(files, dict):
        files = [files]
    if not isinstance(files, list):
        return []

    media_files = [f for f in files if f.get('type') in {'photo', 'video', 'document'}]
    if not media_files:
        return []

    all_saved = []
    for f in media_files:
        path = f['media']
        caption = f.get('caption', '')
        filetype = f.get('type')
        with open(path, 'rb') as fp:
            if filetype == 'video':
                await bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_VIDEO)
                sent = await retry_send(bot.send_video, video=fp, chat_id=DEVELOPER_CHAT_ID, caption=caption)
            elif filetype == 'photo':
                await bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_PHOTO)
                sent = await retry_send(bot.send_photo, photo=fp, chat_id=DEVELOPER_CHAT_ID, caption=caption)
            else:
                await bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_DOCUMENT)
                sent = await retry_send(bot.send_document, document=path, chat_id=DEVELOPER_CHAT_ID, caption=caption)
        if sent is None:
            continue
        processed = process_message(sent, data)
        persist_messages([processed])
        all_saved.append(processed)

    if not all_saved:
        return []

    message = replace_char(data['text_raw'])
    id_str = replace_char(data['idstr'])
    name = data.get('nickname') if data.get('username') == 'favorite' and 'nickname' in data else data['username']
    cleared_name = clear_name(name)
    text = f"\\#{cleared_name}  [{id_str}]({data['url']})\n\n{message}"
    sent_text = await bot.sendMessage(DEVELOPER_CHAT_ID, text, parse_mode=ParseMode.MARKDOWN_V2)
    text_item = process_message(sent_text, data)
    persist_messages([text_item])
    all_saved.append(text_item)
    return all_saved


def dispatch_post_data(data):
    with SEND_LOCK:
        lock_fd = None
        try:
            if fcntl is not None:
                lock_fd = open(LOCK_FILE, 'w')
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            messages = asyncio.run(_send_media_and_text(data))
            return LocalResponse(200, {'messages': messages, '_persisted': True})
        except Exception as e:
            traceback.print_exc()
            return LocalResponse(500, {'error': str(e), '_persisted': False})
        finally:
            if lock_fd and fcntl is not None:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
