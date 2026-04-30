#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram johnmsg 同步与回刷工具

功能：
1. 增量同步 Telegram 消息到 MySQL
2. 支持按 SQL 查询数据库中的消息并重新拉取、刷新数据

安装：
pip install telethon pymysql

示例：
python ops/johnmsg_sync.py sync
python ops/johnmsg_sync.py sync --chat nicejohnbot
python ops/johnmsg_sync.py
python ops/johnmsg_sync.py refresh
python ops/johnmsg_sync.py refresh --sql "message like '%test%'"
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telethon import TelegramClient

from core.database import get_db_conn

api_id = int(os.getenv('TELEGRAM_API_ID', 0))
api_hash = os.getenv('TELEGRAM_API_HASH')

print(api_id, api_hash)
DEFAULT_CHAT = "nicejohnbot"
DEFAULT_REFRESH_SQL = """
message REGEXP '^#([^[:space:]].*)[[:space:]]{2}([^[:space:]]+)nn(.*)$'
ORDER BY chat_id, msg_id
""".strip()

db = get_db_conn()


def init_db():
    with db.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS johnmsg
            (
                chat_id    VARCHAR(100) NOT NULL,
                msg_id     BIGINT       NOT NULL,
                msg_date   DATETIME,
                sender_id  BIGINT,
                message    LONGTEXT,
                raw_text   LONGTEXT,
                has_media  TINYINT(1),
                media_type VARCHAR(30),
                file_name  VARCHAR(500),
                file_size  BIGINT,
                mime_type  VARCHAR(200),
                raw_json   LONGTEXT,
                PRIMARY KEY (chat_id, msg_id),
                KEY idx_date (msg_date),
                KEY idx_media (media_type),
                KEY index_rawjson (raw_json(255)),
                KEY index_message (message(255))
            ) ENGINE = InnoDB
              DEFAULT CHARSET = utf8mb4;
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_state
            (
                chat_id        VARCHAR(100) PRIMARY KEY,
                last_msg_id    BIGINT NOT NULL DEFAULT 0,
                last_sync_time DATETIME
            ) ENGINE = InnoDB
              DEFAULT CHARSET = utf8mb4;
            """
        )


def get_last_msg_id(chat_id):
    with db.cursor() as cur:
        cur.execute(
            "SELECT last_msg_id FROM sync_state WHERE chat_id=%s",
            (chat_id,),
        )
        row = cur.fetchone()
        return row[0] if row else 0


def update_sync_state(chat_id, last_msg_id):
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sync_state(chat_id, last_msg_id, last_sync_time)
            VALUES (%s, %s, NOW())
            ON DUPLICATE KEY UPDATE last_msg_id=%s,
                                    last_sync_time=NOW()
            """,
            (chat_id, last_msg_id, last_msg_id),
        )


def detect_media(msg):
    if not msg.media:
        return 0, "text", None, None, None

    media_type = "text"
    file_name = None
    file_size = None
    mime_type = None

    if msg.photo:
        media_type = "photo"
    elif msg.video:
        media_type = "video"
    elif msg.audio:
        media_type = "audio"
    elif msg.voice:
        media_type = "voice"
    elif msg.document:
        media_type = "document"

    if msg.file:
        file_name = msg.file.name
        file_size = msg.file.size
        mime_type = msg.file.mime_type

    return 1, media_type, file_name, file_size, mime_type


def build_raw_json(msg):
    data = json.loads(msg.to_json())
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def save_message(chat_id, msg, raw_json):
    has_media, media_type, file_name, file_size, mime_type = detect_media(msg)

    with db.cursor() as cur:
        cur.execute(
            """
            REPLACE INTO johnmsg(chat_id, msg_id, msg_date,
                                 sender_id,
                                 message, raw_text,
                                 has_media, media_type,
                                 file_name, file_size, mime_type,
                                 raw_json)
            VALUES (%s, %s, %s,
                    %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s)
            """,
            (
                chat_id,
                msg.id,
                msg.date,
                msg.sender_id,
                msg.message,
                msg.raw_text,
                has_media,
                media_type,
                file_name,
                file_size,
                mime_type,
                raw_json,
            ),
        )


def persist_message(chat_id, msg):
    raw_json = build_raw_json(msg)
    save_message(chat_id, msg, raw_json)


async def sync_chat(client, chat_id):
    entity = await client.get_entity(chat_id)
    last_msg_id = get_last_msg_id(chat_id)

    print(f"开始同步：{chat_id}")
    print(f"上次同步到 msg_id = {last_msg_id}")

    max_msg_id = last_msg_id
    count = 0

    async for msg in client.iter_messages(
            entity,
            reverse=True,
            min_id=last_msg_id,
    ):
        try:
            persist_message(chat_id, msg)
            if msg.id > max_msg_id:
                max_msg_id = msg.id
            count += 1
            print(f"已保存消息 {msg.id}")
        except Exception as exc:
            print("保存失败:", msg.id, exc)

    update_sync_state(chat_id, max_msg_id)

    print("-" * 50)
    print("同步完成")
    print("新增消息数:", count)
    print("最新 msg_id:", max_msg_id)


def get_rows_for_refresh(sql):
    sql = "select chat_id,msg_id from johnmsg where " + sql
    print(sql)
    with db.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


async def refresh_messages(client, sql):
    rows = get_rows_for_refresh(sql)
    total = len(rows)

    print(f"待回刷消息数: {total}")
    if total == 0:
        return

    for index, (row_chat_id, msg_id) in enumerate(rows, start=1):
        try:
            msg = await client.get_messages(row_chat_id, ids=msg_id)
            if not msg:
                print("消息不存在，跳过:", row_chat_id, msg_id)
                continue

            persist_message(row_chat_id, msg)
            print(f"已回刷 {index}/{total}: {row_chat_id} {msg_id}")
        except Exception as exc:
            print("回刷失败:", row_chat_id, msg_id, exc)


def parse_args():
    parser = argparse.ArgumentParser(
        description="johnmsg Telegram 消息同步与回刷工具"
    )
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser("sync", help="增量同步消息")
    sync_parser.add_argument(
        "--chat",
        default=DEFAULT_CHAT,
        help=f"要同步的 chat_id，默认 {DEFAULT_CHAT}",
    )

    refresh_parser = subparsers.add_parser("refresh", help="按 SQL 回刷数据库中的消息")
    refresh_parser.add_argument(
        "--sql",
        default=DEFAULT_REFRESH_SQL,
        help="用于查询 johnmsg 表 chat_id 和 msg_id 的 SQL",
    )

    args = parser.parse_args()
    if args.command is None:
        args.command = "sync"
        args.chat = DEFAULT_CHAT
    return args


async def main():
    args = parse_args()
    init_db()
    if api_id == 0 or api_hash is None:
        raise SystemExit('api_id and api_hash are required.')
    async with TelegramClient("me", api_id, api_hash) as client:
        if args.command == "sync":
            await sync_chat(client, args.chat)
        elif args.command == "refresh":
            await refresh_messages(client, sql=args.sql)


if __name__ == "__main__":
    asyncio.run(main())
