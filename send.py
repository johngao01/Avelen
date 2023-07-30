import asyncio
from datetime import datetime

import telegram
from telegram import Bot, InputMediaVideo, InputMediaPhoto, InputMediaDocument
from telegram.constants import ParseMode

DEVELOPER_CHAT_ID = 708424141
TOKEN = '6572044525:AAH6eRwxAhmhDQo7R7COrWBrZKtG6TqO1rU'
MARKDOWN_CHAR = ['_', '*', '[', '`', ]


async def retry_send(fun, **kwargs):
    time = 5
    while time:
        try:
            r = await fun(**kwargs)
        except telegram.error.TimedOut as e:
            print("Get TimeoutError", e)
            await asyncio.sleep(10)
            time -= 1
        except telegram.error.BadRequest as e:
            print("Get BadRequest Error", e)
            await asyncio.sleep(10)
            time -= 1
        except telegram.error.RetryAfter as e:
            print("Get RetryAfter Error", e)
            await asyncio.sleep(10)
            time -= 1
        else:
            return r


def process_message(message: telegram.Message, weibo_data):
    message_data = {
        'MESSAGE_ID': message.message_id,
        'CAPTION': message.caption or '',
        'CHAT_ID': message.chat_id or '',
        'DATE_TIME': datetime.strftime(message.date, "%Y-%m-%d %H:%M:%S"),
        'FORM_USER': message.from_user.id,
        'CHAT': message.chat.id,
        'MEDIA_GROUP_ID': message.media_group_id or '',
        'TEXT_RAW': weibo_data['text_raw'],
        'WEIBO_URL': weibo_data['weibo_link'],
        'USERID': weibo_data['userid'],
        'WEIBO_IDSTR': weibo_data['idstr'],
        'MBLOGID': weibo_data['mblogid'],
        'PHOTO': {},
        'VIDEO': {},
        'DOCUMENT': {}
    }
    if message.video:
        file = {'file_id': message.video.file_id, 'file_unique_id': message.video.file_unique_id,
                'height': message.video.height, 'width': message.video.width, 'duration': message.video.duration or 0,
                'file_name': message.video.file_name, 'file_size': message.video.file_size or 0,
                'file_type': message.video.mime_type or 'mp4', 'message_id': message.message_id,
                'media_group_id': message.media_group_id, 'weibo_url': weibo_data['weibo_link']}
        message_data['VIDEO'] = file
    if message.photo:
        for photo_size in message.photo:
            file = {'file_id': photo_size.file_id, 'file_unique_id': photo_size.file_unique_id,
                    'width': photo_size.width, 'height': photo_size.height, 'file_size': photo_size.file_size or 0,
                    'file_name': message_data['CAPTION'], 'message_id': message.message_id,
                    'media_group_id': message.media_group_id, 'weibo_url': weibo_data['weibo_link']}
            message_data['PHOTO'][photo_size.file_id] = file
    if message.document:
        file = {'file_id': message.document.file_id, 'file_unique_id': message.document.file_unique_id,
                'file_name': message.document.file_name, 'file_type': message.document.mime_type or '',
                'file_size': message.document.file_size or 0, 'message_id': message.message_id,
                'media_group_id': message.media_group_id, 'weibo_url': weibo_data['weibo_link']}
        message_data['DOCUMENT'] = file
    return message_data


async def send_album(bot, filetype, album: list, ):
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
            print(path, filetype)
            if filetype == 'video':
                media = InputMediaVideo(open(path, mode='rb'), caption=caption)
            elif filetype == 'photo':
                media = InputMediaPhoto(open(path, mode='rb'), caption=caption)
            else:
                media = InputMediaDocument(open(path, mode='rb'), caption=caption)
            medias.append(media)
        send_responses = await retry_send(bot.send_media_group, media=medias, chat_id=DEVELOPER_CHAT_ID)
        if send_responses is not None:
            messages.extend(list(send_responses))
    return messages


async def send_message_after(tg_bot, data, messages):
    message = data['text_raw']
    for char in MARKDOWN_CHAR:
        message = message.replace(char, '\\' + char)
    send_response = await tg_bot.sendMessage(
        DEVELOPER_CHAT_ID,
        "[{}]({})".format(data['username'], data['weibo_link']) + "：" + message,
        parse_mode=ParseMode.MARKDOWN,
    )
    messages.append(send_response)
    results = []
    for send_response in messages:
        result = process_message(send_response, data)
        results.append(result)
    return results


async def send_medias(data):
    tg_bot = Bot(token=TOKEN)
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
        response_message = await send_album(tg_bot, 'photo', photos)
        messages.extend(response_message)
    if len(videos) > 0:
        response_message = await send_album(tg_bot, 'video', videos)
        messages.extend(response_message)
    if len(documents) > 0:
        response_message = await send_album(tg_bot, 'document', documents)
        messages.extend(response_message)
    results = await send_message_after(tg_bot, data, messages)
    return results


async def send_video_or_photo(data):
    tg_bot = Bot(token=TOKEN)
    file = data['files']
    caption = file['caption']
    path = file['media']
    ext = path[-3:]
    print(path)
    if ext in ['mp4', 'mov', 'gif']:
        send_response = await retry_send(fun=tg_bot.send_video, video=path, chat_id=DEVELOPER_CHAT_ID, caption=caption)
    else:
        send_response = await retry_send(fun=tg_bot.send_photo, video=path, chat_id=DEVELOPER_CHAT_ID, caption=caption)
    messages = [send_response]
    results = await send_message_after(tg_bot, data, messages)
    return results


async def message_send(data):
    tg_bot = Bot(token=TOKEN)
    message = data['message']
    for char in MARKDOWN_CHAR:
        message = message.replace(char, '\\' + char)
    send_response = await retry_send(tg_bot.sendMessage, chat_id=DEVELOPER_CHAT_ID, text=message,
                                     parse_mode=ParseMode.MARKDOWN)
    result = process_message(send_response, data)
    return result


async def send_document(data):
    tg_bot = Bot(token=TOKEN)
    file = data['files']
    caption = file['caption']
    path = file['media']
    send_response = await retry_send(tg_bot.send_document, chat_id=DEVELOPER_CHAT_ID, document=path,
                                     caption=caption)
    result = process_message(send_response, data)
    return result
