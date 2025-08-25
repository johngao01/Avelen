import datetime
import os
import sys
from telethon.sync import TelegramClient
from telethon import functions
from re import sub
import pickle
from loguru import logger
# 替换为你的 API ID 和 HASH
  

api_id = 22203014
api_hash = '6b373c6531660f41b039d5d85d703f4f'
media_group_dict = {}
target_chat_id = 'MMN520'
download_root_dir = '/root/download'
download_count = 0
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time} | {level} | {message}")
logger.add(
    f"logs/{target_chat_id}.log",
    filter=lambda record: record["extra"].get("name") == "download"
)
download_logger = logger.bind(name="download")
def download(message, media_group):
    if not message.media:
        return
    msg_time = message.date.strftime('%Y%m%d_%H%M%S')
    if message.file:
        suffix = f"{msg_time}{message.file.ext}"
    else:
        suffix = f"{msg_time}"
    filename = message.file.name or f'{message.id}_{suffix}'
    dirname = sub('[\\\\/:*?"<>|\n]', "", media_group_dict[media_group]['text'])
    if not dirname:
        dirname = '未分类'
    save_dir = os.path.join(download_root_dir, target_chat_id , dirname)
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, filename)
    if filename == 'V.mov':
        return
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        pass
    else:
        with open(filepath, 'wb') as f1:
            f1.write(client.download_file(message.media))
    global download_count
    if os.path.exists(filepath):
        download_count += 1
        print(f"{message.id} 下载成功: {filepath}, 文件大小: {os.path.getsize(filepath)} bytes")
    else:
        download_count += 1
        print(f"{message.id} 下载失败: {filepath}, 文件可能不存在或下载失败")


def get_chat_history(client, chat):
    # 获取一个聊天的聊天记录
    entity = client.get_entity(chat)
    for message in client.iter_messages(entity, reverse=True, min_id=31906-1):
        try:
            if not message.media:
                print("此消息无媒体内容:", message.id, message.text)
                continue
            media_group = message.grouped_id
            if not media_group:
                print("此消息为独立消息:", message.id, message.text)
                continue
            if media_group in media_group_dict:
                media_group_dict[media_group]['messages'].append(str(message.id))
            else:
                media_group_dict[media_group] = {
                    'text': message.text,
                    'id': str(message.id),
                    'messages': [str(message.id)]
                }
                download_logger.info(f"{message.id}\t{message.text}")
            download(message, media_group)
            if message.replies:
                replies = client(functions.messages.GetRepliesRequest(
                    peer=entity,
                    msg_id=message.id,
                    offset_id=0,
                    offset_date=None,
                    add_offset=0,
                    limit=200,
                    max_id=0,
                    min_id=0,
                    hash=0
                ))
                for reply_msg in replies.messages:
                    download(reply_msg, media_group)
        except Exception as e:
            print("发生错误", message.id, str(e))
        if download_count % 6666 == 0:
            print(f"已下载 {download_count} 个文件，当前处理的消息ID: {message.id}")
            print(f"暂停5分钟")
            import time
            print(datetime.datetime.now())
            time.sleep(600)


def get_message_by_id(client, chat_id, message_id):
    # 根据消息id获取消息
    chat = client.get_entity(chat_id)
    messages = client.get_messages(chat, ids=message_id)
    # telethon.tl.patched.Message
    return messages


with TelegramClient('me', api_id, api_hash) as client:
    get_chat_history(client, f'https://t.me/{target_chat_id}')
    with open('data.pkl', 'wb') as f:
        pickle.dump(media_group_dict, f)
