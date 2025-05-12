import re
import time
import traceback
from datetime import datetime

import emoji
import telegram
from telegram import Bot, InputMediaVideo, InputMediaPhoto, InputMediaDocument
from telegram.constants import ParseMode
from telegram.constants import ChatAction

DEVELOPER_CHAT_ID = 708424141
TOKEN = '6572044525:AAH6eRwxAhmhDQo7R7COrWBrZKtG6TqO1rU'
API_URL = 'http://localhost:8081/bot'
FILE_API_URL = 'http://localhost:8081/file/bot'
MARKDOWN_CHAR = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']


def clear_name(text):
    # 去除中英文小括号及其内容
    result = re.sub(r'[（(【].*?[】)）]', '', text)
    # 去除表情
    result = emoji.demojize(result)
    result = re.sub(':\S+?:', '', result)
    # 只保留字母、数字、下划线，其余全部删除
    result = re.sub(r'[^\w]', '', result)
    result = result.replace('_', '\_')
    if result == '':
        return '没有名字'
    return result


def replace_char(text):
    for char in MARKDOWN_CHAR:
        text = text.replace(char, f'\\{char}')
    return text


async def retry_send(fun, **kwargs) -> list:
    try:
        r = await fun(**kwargs, read_timeout=42, write_timeout=40, connect_timeout=40, pool_timeout=40)
        return r
    except telegram.error.TimedOut:
        print("Get TimeoutError：\n" + traceback.format_exc())
    except telegram.error.BadRequest:
        print("Get BadRequest Error：\n" + traceback.format_exc())
    except telegram.error.RetryAfter as e:
        if 'Flood control exceeded. Retry in' in e.message:
            second = int(e.message.split(' ')[-2])
            print("sleep {} seconds".format(second))
            time.sleep(second)
        print("Get RetryAfter Error：\n" + traceback.format_exc())
    return []


def process_message(message: telegram.Message, data):
    if data['username'] == 'favorite' and 'nickname' in data:
        username = data['nickname']
    else:
        username = data['username']
    message_data = {
        'MESSAGE_ID': message.message_id,
        'CAPTION': message.caption or '',
        'CHAT_ID': message.chat_id or '',
        'DATE_TIME': datetime.strftime(message.date, "%Y-%m-%d %H:%M:%S"),
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
        file = {'file_id': message.video.file_id, 'file_unique_id': message.video.file_unique_id,
                'height': message.video.height, 'width': message.video.width, 'duration': message.video.duration or 0,
                'file_name': message.video.file_name, 'file_size': message.video.file_size or 0,
                'file_type': message.video.mime_type or 'mp4', 'message_id': message.message_id,
                'media_group_id': message.media_group_id, 'url': data['url']}
        message_data['VIDEO'] = file
    if message.photo:
        for photo_size in message.photo:
            file = {'file_id': photo_size.file_id, 'file_unique_id': photo_size.file_unique_id,
                    'width': photo_size.width, 'height': photo_size.height, 'file_size': photo_size.file_size or 0,
                    'file_name': message_data['CAPTION'], 'message_id': message.message_id,
                    'media_group_id': message.media_group_id, 'url': data['url']}
            message_data['PHOTO'][photo_size.file_id] = file
    if message.document:
        file = {'file_id': message.document.file_id, 'file_unique_id': message.document.file_unique_id,
                'file_name': message.document.file_name, 'file_type': message.document.mime_type or '',
                'file_size': message.document.file_size or 0, 'message_id': message.message_id,
                'media_group_id': message.media_group_id, 'url': data['url']}
        message_data['DOCUMENT'] = file
    return message_data


async def send_album(bot, filetype, album: list):
    def rearrange_files(file_list):
        result_lists = []
        current_list = []
        current_size = 0

        for file in file_list:
            size = file[-1]
            if len(current_list) < 10 and current_size + size <= 50 * 1024 * 1024:
                current_list.append(file)
                current_size += size
            else:
                result_lists.append(current_list)
                current_list = [file]
                current_size = size

        if current_list:
            result_lists.append(current_list)

        return result_lists

    albums = rearrange_files(album)
    messages = []

    for album in albums:
        medias = []
        for media in album:
            path, caption, file_size = media
            print(path + "\t" + filetype)
            with open(path, 'rb') as f:
                if filetype == 'video':
                    media = InputMediaVideo(f, caption=caption)
                elif filetype == 'photo':
                    media = InputMediaPhoto(f, caption=caption)
                else:
                    media = InputMediaDocument(f, caption=caption)
            medias.append(media)
        send_responses = await retry_send(bot.send_media_group, media=medias, chat_id=DEVELOPER_CHAT_ID)
        if send_responses is not None:
            messages.extend(list(send_responses))
    return messages


async def send_message_after(tg_bot, data, messages):
    message = data['text_raw']
    message = replace_char(message)
    id_str = replace_char(data['idstr'])
    if data['username'] == 'favorite' and 'nickname' in data:
        name = data['nickname']
    else:
        name = data['username']
    cleared_name = clear_name(name)
    text = f"\#{cleared_name}  [{id_str}]({data['url']})\n\n{message}"
    send_response = await tg_bot.sendMessage(
        DEVELOPER_CHAT_ID,
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    messages.append(send_response)
    results = []
    for send_response in messages:
        result = process_message(send_response, data)
        results.append(result)
    return results


async def send_multiple(data):
    tg_bot = Bot(token=TOKEN, local_mode=True, base_url=API_URL, base_file_url=FILE_API_URL)
    photos = []
    videos = []
    documents = []
    files = data['files']
    messages = []
    for file in files:
        caption = file['caption']
        path = file['media']
        size = file['size']
        filetype = file['type']
        if filetype == 'video':
            videos.append([path, caption, size])
        elif filetype == 'photo':
            photos.append([path, caption, size])
        elif filetype == 'document':
            documents.append([path, caption, size])
        elif filetype == 'url':
            send_response = await retry_send(tg_bot.sendMessage, chat_id=DEVELOPER_CHAT_ID, text=file['send_url'],
                                             parse_mode=ParseMode.MARKDOWN)
            messages.append(send_response)
    if len(photos) > 0:
        await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_PHOTO)
        response_message = await send_album(tg_bot, 'photo', photos)
        messages.extend(response_message)
    if len(videos) > 0:
        await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_VIDEO)
        response_message = await send_album(tg_bot, 'video', videos)
        messages.extend(response_message)
    if len(documents) > 0:
        await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_DOCUMENT)
        response_message = await send_album(tg_bot, 'document', documents)
        messages.extend(response_message)
    results = await send_message_after(tg_bot, data, messages)
    return results


async def send_single(data):
    tg_bot = Bot(token=TOKEN, local_mode=True, base_url=API_URL, base_file_url=FILE_API_URL)
    file = data['files']
    caption = file['caption']
    path = file['media']
    filetype = file['type']
    ext = path.split('.')[-1]
    print(path + "\t" + ext)
    with open(path, 'rb') as f:
        if filetype == 'document':
            await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_DOCUMENT)
            send_response = await retry_send(tg_bot.send_document, chat_id=DEVELOPER_CHAT_ID, document=path,
                                             caption=caption)
        else:
            if ext in ['mp4', 'mov', 'gif']:
                await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_VIDEO)
                send_response = await retry_send(fun=tg_bot.send_video, video=f, chat_id=DEVELOPER_CHAT_ID,
                                                 caption=caption)
            else:
                await tg_bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.UPLOAD_PHOTO)
                send_response = await retry_send(fun=tg_bot.send_photo, photo=f, chat_id=DEVELOPER_CHAT_ID,
                                                 caption=caption)
    if send_response is None:
        print("send_single发送失败，", path)
        return
    messages = [send_response]
    results = await send_message_after(tg_bot, data, messages)
    return results


async def backup():
    tg_bot = Bot(token=TOKEN, local_mode=True, base_url=API_URL, base_file_url=FILE_API_URL)
    with open('/root/pythonproject/weibo_tg_bot/sqlite.db', 'rb') as f:
        await retry_send(tg_bot.send_document, chat_id=DEVELOPER_CHAT_ID, document=f)
