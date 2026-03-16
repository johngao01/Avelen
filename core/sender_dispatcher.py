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
from dataclasses import dataclass
from datetime import datetime
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
    return item


def persist_messages(messages: list[telegram.Message], data):
    """将 telegram 返回消息结构落库（messages/video/photo/document）。"""
    if not messages:
        return
    conn = get_db_conn()
    try:
        for m in messages:
            send_response_dict = process_message(m, data)
            insert_data(conn, 'messages', MESSAGES, send_response_dict)
    finally:
        conn.close()


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

        # [需求3]：发送文件后，立即处理返回的 message
        persist_messages([res], data)

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

                persist_messages(res_msgs, data)

            finally:
                # 确保清理释放所有打开的文件资源
                for f in open_files:
                    f.close()


async def execute_task(data):
    tg_bot = Bot(token=TOKEN, local_mode=True, base_url=API_URL, base_file_url=FILE_API_URL)
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

        persist_messages(send_response, data)

    return processed_results


def dispatch_post_data(data: dict):
    """统一分发入口：进程锁 + 文件锁，保证跨爬虫串行发送。
        post_data = {
            'username': '',  # 数据库中的用户名
            'nickname': '',  # 实际用户名
            'url': '',  # post的url地址
            'userid': '',  # 用户id
            'idstr': '',  # post的id
            'mblogid': '',  # post的id，微博才有，其它平台没有
            'create_time': '',  # post的发布时间
            'text_raw': '',  # post的文案
            'files': [{
                'media': '',  # 文件本地保存地址，绝对路径
                'type': ''  # 文件类型 video photo document
            }]
        }
    """
    lock = FileLock(LOCK_FILE, timeout=3600)
    with lock:
        try:
            messages = asyncio.run(execute_task(data))
            return LocalResponse(200, {'messages': messages, '_persisted': True})
        except Exception as e:
            traceback.print_exc()
            return LocalResponse(500, {'error': str(e), '_persisted': False})


