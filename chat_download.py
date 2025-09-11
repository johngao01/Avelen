#!/usr/bin/env python3
import asyncio
import datetime
import os
import sys
import pickle
import json
from re import sub

from loguru import logger
from telethon import TelegramClient, functions
from FastTelethonhelper import fast_download, human_readable_size  # 异步函数

# ========== 配置区 ==========
api_id = 22203014
api_hash = '6b373c6531660f41b039d5d85d703f4f'
download_root_dir = '/root/download'
# ============================
with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)
media_group_dict = {}
download_count = 0
BIG_FILE = 10 * 1024 * 1024 * 1024 





async def download(client: TelegramClient, message, media_group, chat_id):
    """
    异步下载单条消息的 media。
    使用 fast_download 处理大文件（视频等），小图片直接用 client.download_media。
    """
    global download_count

    if not getattr(message, "media", None):
        return

    # 文件名
    msg_time = message.date.strftime('%Y%m%d_%H%M%S')
    suffix = f"{msg_time}{getattr(message.file, 'ext', '')}" if getattr(message, "file", None) else msg_time
    filename = (message.file.name if getattr(message, "file", None) and message.file.name else f'{message.id}_{suffix}')

    # 目录名（安全过滤）
    dirname = sub(r'[\\/:*?"<>|\n]', "", media_group_dict.get(media_group, {}).get('text', ''))
    if not dirname:
        dirname = '未分类'

    save_dir = os.path.join(download_root_dir, chat_id, dirname)
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, filename)
    file_size = message.file.size
    try:
        # 若已存在且大小 >0 则跳过下载
        if os.path.exists(filepath) and os.path.getsize(filepath) == file_size:
            pass
        else:
            try:
                if file_size > BIG_FILE:
                    r = await message.reply("Downloading..")
                    # 大文件使用 fast_download（它是异步的）
                    await fast_downrload(client, message, r, filepath)
                else:
                    # 小文件用内置的下载方法（可靠）
                    await client.download_media(message, file=filepath)
            except Exception as e:
                download_logger.error(f"下载异常 message_id={getattr(message,'id',None)} error={e}")
    except Exception as e:
        download_logger.error(f"处理文件时发生错误 message_id={getattr(message,'id',None)} error={e}")

    # 统计并打印结果
    download_count += 1
    if os.path.exists(filepath) and os.path.getsize(filepath) == file_size:
        print(f"{message.id} 下载成功: {filepath}, 文件大小: {human_readable_size(file_size)}")
    else:
        print(f"{message.id} 下载失败: {filepath}, 文件可能不存在或下载失败")


async def get_chat_history(client: TelegramClient, chat_id, min_id_start):
    """
    异步遍历 chat 历史并下载 media。
    """
    global media_group_dict, download_count, data
    # 日志配置
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time} | {message}")
    logger.add(
        f"logs/{chat_id}.log",
        filter=lambda record: record["extra"].get("name") == "download",
        format="{time} | {message}"
    )
    download_logger = logger.bind(name="download")
    chat = f'https://t.me/{chat_id}'
    entity = await client.get_entity(chat)

    async for message in client.iter_messages(entity, reverse=True, min_id=min_id_start-1):
        just_download = ''
        try:
            if not getattr(message, "media", None):
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
                    'text': message.text or '',
                    'id': str(message.id),
                    'messages': [str(message.id)]
                }
                download_logger.info(f"{message.id}\t{message.date.strftime('%Y-%m-%d %H:%M:%S')}\t{message.text}")
                data[chat_id]['min_id'] = message.id
                if message.text not in data[chat_id]['download_history']:
                    data[chat_id]['download_history'].append(message.text)
                with open("data.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)

            await download(client, message, media_group, chat_id)

            # 如果有回复，也下载回复里的媒体
            if message.replies:
                replies = await client(functions.messages.GetRepliesRequest(
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
                    await download(client, reply_msg, media_group, chat_id)

        except Exception as e:
            print("发生错误", getattr(message, "id", None), str(e))

        # 定期休息（异步不会阻塞事件循环）
        if download_count != 0 and download_count % 6666 == 0:
            print(f"已下载 {download_count} 个文件，当前处理的消息ID: {message.id}")
            print("暂停5分钟")
            print(datetime.datetime.now())
            await asyncio.sleep(600)


async def main():
    # 使用异步客户端
    async with TelegramClient('me', api_id, api_hash) as client:
        
        for k,v in data.items():
            await get_chat_history(client, k, v['min_id'])
            # 保存 media_group_dict
            with open('data.pkl', 'wb') as f:
                pickle.dump(media_group_dict, f)
            print("全部完成，media_group_dict 已保存到 data.pkl")


if __name__ == '__main__':

    asyncio.run(main())
