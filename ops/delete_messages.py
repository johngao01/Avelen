import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import telegram.error
from loguru import logger
from telegram import Bot

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.database import get_db_conn
from core.settings import LOGS_DIR, DOWNLOAD_ROOT

DELETE_WINDOW_HOURS = 48
DB_UTC_OFFSET_HOURS = 8

logger.remove()
logger.add(
    sys.stderr,
    format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
    level='INFO',
)
logger.add(
    str(LOGS_DIR / 'delete_messages.log'),
    format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
    level='INFO',
    encoding='utf-8',
)


@dataclass(slots=True)
class MessageRow:
    """messages 表中删除脚本关心的字段快照。"""
    message_id: int
    caption: str
    chat_id: str
    date_time: str
    media_group_id: str
    text_raw: str
    url: str
    userid: str
    username: str
    idstr: str
    mblogid: str
    msg_str: str

    @property
    def is_media_message(self) -> bool:
        return bool((self.caption or '').strip())


@dataclass(slots=True)
class PostGroup:
    """按单条 post 聚合后的消息和候选文件。"""
    post_key: str
    rows: list[MessageRow]
    matched_files: dict[str, list[Path]]

    @property
    def sample(self) -> MessageRow:
        return self.rows[0]

    @property
    def message_ids(self) -> list[int]:
        return [row.message_id for row in self.rows]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='根据 SQL 条件删除 messages 表记录关联的 Telegram 消息和已下载文件。'
    )
    parser.add_argument(
        '--where',
        required=True,
        help='附加到 `WHERE 1=1 AND (...)` 的 SQL 条件，例如 `URL=%%s AND USERNAME=%%s`',
    )
    parser.add_argument(
        '--param',
        action='append',
        default=[],
        help='按顺序提供 SQL 参数，可重复传入多次，例如 `--param https://... --param user1`',
    )
    parser.add_argument('--delete-db', action='store_true', help='执行时额外删除 messages 表记录；默认不删数据库')
    parser.add_argument('--skip-telegram', action='store_true', help='跳过 Telegram 删除')
    parser.add_argument('--skip-files', action='store_true', help='跳过本地文件删除')
    parser.add_argument('--execute', action='store_true', help='真正执行删除；默认只预览')
    return parser


def build_query(args: argparse.Namespace) -> tuple[str, tuple[Any, ...]]:
    # Telegram Bot 常见删除窗口是近 48 小时；数据库里 DATE_TIME 按 UTC 入库，
    # 而当前服务器时间是东八区，所以查询时额外回拨 8 小时，实际取最近 56 小时。
    date_time_start = (datetime.now() - timedelta(hours=DELETE_WINDOW_HOURS + DB_UTC_OFFSET_HOURS)).strftime(
        '%Y-%m-%d %H:%M:%S'
    )
    sql = f'''
        SELECT
            MESSAGE_ID,
            COALESCE(CAPTION, ''),
            COALESCE(CHAT_ID, ''),
            COALESCE(DATE_TIME, ''),
            COALESCE(MEDIA_GROUP_ID, ''),
            COALESCE(TEXT_RAW, ''),
            COALESCE(URL, ''),
            COALESCE(USERID, ''),
            COALESCE(USERNAME, ''),
            COALESCE(IDSTR, ''),
            COALESCE(MBLOGID, ''),
            COALESCE(MSG_STR, '')
        FROM messages
        WHERE 1=1
          AND DATE_TIME >= %s
          AND ({args.where})
        ORDER BY
            COALESCE(IDSTR, ''),
            COALESCE(DATE_TIME, ''),
            MESSAGE_ID
    '''
    return sql, (date_time_start, *args.param)


def fetch_rows(args: argparse.Namespace) -> list[MessageRow]:
    sql, params = build_query(args)
    conn = get_db_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
    finally:
        conn.close()
    return [MessageRow(*row) for row in rows]


def collect_files_for_rows(rows: list[MessageRow]) -> dict[str, list[Path]]:
    # 发送入库时媒体 caption 默认就是落地文件名，这里直接反查下载目录。
    candidate_names = sorted({
        row.caption.strip()
        for row in rows
        if row.is_media_message and row.caption.strip()
    })
    matched: dict[str, list[Path]] = {}
    root = Path(DOWNLOAD_ROOT)
    for name in candidate_names:
        matched[name] = [path for path in root.rglob(name) if path.is_file()]
    return matched


def iter_post_groups(rows: list[MessageRow], *, skip_files: bool) -> Iterator[PostGroup]:
    # SQL 已经按 IDSTR 排序，这里顺序扫描即可流式切分 post，
    # 不需要先把所有消息做一次全量 groupby 再统一处理。
    current_rows: list[MessageRow] = []
    current_key: str | None = None

    for row in rows:
        row_key = row.idstr
        if current_key is None:
            current_key = row_key
        if row_key != current_key and current_key:
            ordered_rows = sorted(current_rows, key=lambda item: (item.date_time, item.message_id))
            matched_files = {} if skip_files else collect_files_for_rows(ordered_rows)
            yield PostGroup(post_key=current_key, rows=ordered_rows, matched_files=matched_files)
            current_rows = []
            current_key = row_key
        current_rows.append(row)

    if current_rows and current_key is not None:
        ordered_rows = sorted(current_rows, key=lambda item: (item.date_time, item.message_id))
        matched_files = {} if skip_files else collect_files_for_rows(ordered_rows)
        yield PostGroup(post_key=current_key, rows=ordered_rows, matched_files=matched_files)


def count_total_posts(rows: list[MessageRow]) -> int:
    # 只按 idstr 计数，保证进度显示是 current_post/total_post。
    total_posts = 0
    previous_key: str | None = None
    for row in rows:
        current_key = row.idstr
        if current_key != previous_key:
            total_posts += 1
            previous_key = current_key
    return total_posts


def build_bot() -> Bot:
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is required')
    return Bot(token=token)


async def delete_telegram_for_post(group: PostGroup) -> tuple[list[int], list[tuple[int, str]]]:
    bot = build_bot()
    message_ids = group.message_ids
    chat_id = group.sample.chat_id
    logger.info(f'开始删除 Telegram 消息: post={group.post_key}, chat_id={chat_id}, message_ids={message_ids}')
    try:
        # 一个 post 的消息一次性批量删，避免逐条 delete_message 带来的额外 RTT。
        await bot.delete_messages(chat_id=chat_id, message_ids=message_ids)
        logger.info(f'Telegram 消息删除完成: post={group.post_key}, count={len(message_ids)}')
        return message_ids, []
    except telegram.error.TelegramError as exc:
        logger.error(f'Telegram 消息删除失败: post={group.post_key}, error={exc}')
        return [], [(message_id, str(exc)) for message_id in message_ids]


def delete_files_for_post(group: PostGroup) -> tuple[list[Path], list[tuple[Path, str]]]:
    deleted: list[Path] = []
    failed: list[tuple[Path, str]] = []
    for name, paths in group.matched_files.items():
        if not paths:
            logger.warning(f'未找到待删文件: post={group.post_key}, caption={name}')
            continue
        for path in paths:
            try:
                logger.info(f'删除本地文件: post={group.post_key}, path={path}')
                path.unlink()
                deleted.append(path)
            except OSError as exc:
                logger.error(f'删除本地文件失败: post={group.post_key}, path={path}, error={exc}')
                failed.append((path, str(exc)))
    return deleted, failed


def delete_db_rows_for_post(group: PostGroup) -> int:
    message_ids = group.message_ids
    if not message_ids:
        return 0
    placeholders = ','.join(['%s'] * len(message_ids))
    sql = f'DELETE FROM messages WHERE MESSAGE_ID IN ({placeholders})'
    conn = get_db_conn()
    try:
        with conn.cursor() as cursor:
            affected = cursor.execute(sql, tuple(message_ids))
        conn.commit()
        logger.info(f'数据库记录删除完成: post={group.post_key}, affected={affected}, message_ids={message_ids}')
        return affected
    finally:
        conn.close()


def print_group_preview(group: PostGroup, index: int, total: int | None = None) -> None:
    sample = group.sample
    print('-' * 80)
    if total is None:
        print(f'进度(progress): {index}')
    else:
        print(f'进度(progress): {index}/{total}')
    print(f'键(key): {group.post_key}')
    print(f'用户(username): {sample.username}')
    print(f'用户ID(userid): {sample.userid}')
    print(f'链接(url): {sample.url}')
    print(f'idstr: {sample.idstr}')
    print(f'mblogid: {sample.mblogid}')
    print(f'消息ID(message_ids): {", ".join(str(message_id) for message_id in group.message_ids)}')
    if group.matched_files:
        matched_paths = [str(path) for paths in group.matched_files.values() for path in paths]
        if matched_paths:
            print(f'本地文件(files): {", ".join(matched_paths)}')
        unresolved = [name for name, paths in group.matched_files.items() if not paths]
        if unresolved:
            print(f'未找到文件(missing_files): {", ".join(unresolved)}')
    sys.stdout.flush()


def print_execution_summary(
        total_posts: int,
        total_rows: int,
        telegram_deleted: list[int],
        telegram_failed: list[tuple[int, str]],
        file_deleted: list[Path],
        file_failed: list[tuple[Path, str]],
        db_deleted: int,
) -> None:
    print('')
    print('执行结果(Execute)')
    print(f'  目标消息数(target_messages): {total_rows}')
    print(f'  目标帖子组(target_posts): {total_posts}')
    print(f'  Telegram 删除成功(telegram_deleted): {len(telegram_deleted)}')
    print(f'  Telegram 删除失败(telegram_failed): {len(telegram_failed)}')
    print(f'  本地文件删除成功(files_deleted): {len(file_deleted)}')
    print(f'  本地文件删除失败(files_failed): {len(file_failed)}')
    print(f'  数据库删除行数(db_deleted): {db_deleted}')
    if telegram_failed:
        print('')
        print('Telegram 删除失败列表：')
        for message_id, error in telegram_failed:
            print(f'  - {message_id}: {error}')
    if file_failed:
        print('')
        print('文件删除失败列表：')
        for path, error in file_failed:
            print(f'  - {path}: {error}')


def execute_group(group: PostGroup, args: argparse.Namespace) -> tuple[
    list[int], list[tuple[int, str]], list[Path], list[tuple[Path, str]], int]:
    telegram_deleted: list[int] = []
    telegram_failed: list[tuple[int, str]] = []
    file_deleted: list[Path] = []
    file_failed: list[tuple[Path, str]] = []
    db_deleted = 0

    logger.info(f'开始处理 post: key={group.post_key}, message_ids={group.message_ids}')

    # 删除顺序固定为：Telegram -> 文件 -> 数据库。
    if not args.skip_telegram:
        deleted, failed = asyncio.run(delete_telegram_for_post(group))
        telegram_deleted.extend(deleted)
        telegram_failed.extend(failed)

    if not args.skip_files:
        deleted_files, failed_files = delete_files_for_post(group)
        file_deleted.extend(deleted_files)
        file_failed.extend(failed_files)

    if args.delete_db:
        db_deleted += delete_db_rows_for_post(group)

    logger.info(f'处理结束 post: key={group.post_key}')
    return telegram_deleted, telegram_failed, file_deleted, file_failed, db_deleted


def process_stream(rows: list[MessageRow], args: argparse.Namespace) -> None:
    telegram_deleted: list[int] = []
    telegram_failed: list[tuple[int, str]] = []
    file_deleted: list[Path] = []
    file_failed: list[tuple[Path, str]] = []
    db_deleted = 0
    total_posts = count_total_posts(rows)
    total_rows = len(rows)
    current_post = 0

    for group in iter_post_groups(rows, skip_files=args.skip_files):
        current_post += 1
        print_group_preview(group, current_post, total_posts)
        if args.execute:
            deleted, failed, deleted_files, failed_files, deleted_db = execute_group(group, args)
            telegram_deleted.extend(deleted)
            telegram_failed.extend(failed)
            file_deleted.extend(deleted_files)
            file_failed.extend(failed_files)
            db_deleted += deleted_db

    if not args.execute:
        print('')
        print('当前为预览模式。确认无误后，加上 --execute 进行实际删除。')
        if not args.delete_db:
            print('如需同步清理 messages 表记录，再额外加上 --delete-db。')
        return

    print_execution_summary(
        total_posts=total_posts,
        total_rows=total_rows,
        telegram_deleted=telegram_deleted,
        telegram_failed=telegram_failed,
        file_deleted=file_deleted,
        file_failed=file_failed,
        db_deleted=db_deleted,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rows = fetch_rows(args)
    if not rows:
        logger.info('没有匹配到任何 messages 记录。')
        print('没有匹配到任何 messages 记录。')
        return

    logger.info(
        f'命中待处理消息记录: messages={len(rows)}, '
        f'skip_telegram={args.skip_telegram}, skip_files={args.skip_files}, '
        f'delete_db={args.delete_db}, execute={args.execute}, '
        f'delete_window_hours={DELETE_WINDOW_HOURS}, db_utc_offset_hours={DB_UTC_OFFSET_HOURS}'
    )
    process_stream(rows, args)


if __name__ == '__main__':
    main()
