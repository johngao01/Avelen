import argparse
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.database import get_db_conn


@dataclass(slots=True)
class MessageRow:
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

    @property
    def is_text_message(self) -> bool:
        return (self.caption or '') == ''

    @property
    def is_media_message(self) -> bool:
        return not self.is_text_message


@dataclass(slots=True)
class PostCheckResult:
    post_key: str
    url: str
    idstr: str
    mblogid: str
    username: str
    userid: str
    total_messages: int
    media_count: int
    text_count: int
    status: str
    detail: str
    ordered_types: list[str]
    message_ids: list[int]


STATUS_LABELS = {
    'complete': '完整发送(complete)',
    'misordered': '错位发送(misordered)',
    'missing': '漏发送(missing)',
    'duplicate_send': '重复发送(duplicate_send)',
    'unknown': '未知(unknown)',
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='检查 messages 表中每个 post 的 Telegram 发送是否完整、错位或漏发。'
    )
    parser.add_argument('--url', help='只检查指定 URL')
    parser.add_argument('--idstr', help='只检查指定 idstr')
    parser.add_argument('--mblogid', help='只检查指定 mblogid')
    parser.add_argument('--userid', help='只检查指定 userid')
    parser.add_argument('--username', help='只检查指定 username')
    parser.add_argument('--date-time-start', dest='date_time_start', help='date_time 起始时间，格式 YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--date-time-end', dest='date_time_end', help='date_time 结束时间，格式 YYYY-MM-DD HH:MM:SS')
    parser.add_argument(
        '--status',
        choices=['complete', 'misordered', 'missing', 'duplicate_send', 'unknown'],
        help='只输出指定状态',
    )
    parser.add_argument('--limit', type=int, default=200, help='最多输出多少个 post，默认 200')
    parser.add_argument('--show-complete', action='store_true', help='默认只输出异常；加上此参数后输出完整记录')
    parser.add_argument('--summary-only', action='store_true', help='只输出汇总')
    return parser


def fetch_rows(args: argparse.Namespace) -> list[MessageRow]:
    where_clauses = ['1=1']
    params: list[Any] = []
    has_time_filter = any([
        args.date_time_start,
        args.date_time_end,
    ])

    if args.url:
        where_clauses.append('URL=%s')
        params.append(args.url)
    if args.idstr:
        where_clauses.append('IDSTR=%s')
        params.append(args.idstr)
    if args.mblogid:
        where_clauses.append('MBLOGID=%s')
        params.append(args.mblogid)
    if args.userid:
        where_clauses.append('USERID=%s')
        params.append(args.userid)
    if args.username:
        where_clauses.append('USERNAME=%s')
        params.append(args.username)
    if args.date_time_start:
        where_clauses.append('DATE_TIME >= %s')
        params.append(args.date_time_start)
    if args.date_time_end:
        where_clauses.append('DATE_TIME <= %s')
        params.append(args.date_time_end)
    if not has_time_filter:
        default_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        where_clauses.append('DATE_TIME >= %s')
        params.append(default_start)

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
            COALESCE(MBLOGID, '')
        FROM messages
        WHERE {' AND '.join(where_clauses)}
        ORDER BY
            COALESCE(URL, ''),
            COALESCE(DATE_TIME, ''),
            MESSAGE_ID
    '''

    conn = get_db_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
    finally:
        conn.close()

    return [MessageRow(*row) for row in rows]


def build_post_key(row: MessageRow) -> str:
    if row.url:
        return f'url:{row.url}'
    if row.idstr:
        return f'idstr:{row.idstr}'
    if row.mblogid:
        return f'mblogid:{row.mblogid}'
    return f'fallback:{row.userid}|{row.username}|{row.date_time}'


def classify_post(rows: list[MessageRow]) -> PostCheckResult:
    ordered_rows = sorted(rows, key=lambda item: (item.date_time, item.message_id))
    ordered_types = ['text' if row.is_text_message else 'media' for row in ordered_rows]
    media_rows = [row for row in ordered_rows if row.is_media_message]
    text_rows = [row for row in ordered_rows if row.is_text_message]

    media_count = len(media_rows)
    text_count = len(text_rows)
    first_text_index = next((index for index, item in enumerate(ordered_types) if item == 'text'), -1)

    if media_count == 0 and text_count == 0:
        status = 'unknown'
        detail = '没有可识别的消息记录'
    elif media_count == 0:
        status = 'missing'
        detail = '缺少媒体消息，只发送了文字'
    elif text_count == 0:
        status = 'missing'
        detail = '缺少文字消息，只发送了媒体'
    elif first_text_index == 0:
        if media_count > 0:
            status = 'misordered'
            detail = '文字先于媒体发送，属于错位发送'
        else:
            status = 'missing'
            detail = '缺少媒体消息，只发送了文字'
    elif text_count > 1:
        status = 'duplicate_send'
        detail = f'文字消息发送了 {text_count} 次，存在重复发送脏数据'
    elif first_text_index != len(ordered_types) - 1:
        status = 'duplicate_send'
        detail = '在一套媒体+文字发送完成后又继续发送了消息，存在重复发送脏数据'
    else:
        status = 'complete'
        detail = '媒体先发，文字后发，记录完整'

    sample = ordered_rows[0]
    return PostCheckResult(
        post_key=build_post_key(sample),
        url=sample.url,
        idstr=sample.idstr,
        mblogid=sample.mblogid,
        username=sample.username,
        userid=sample.userid,
        total_messages=len(ordered_rows),
        media_count=media_count,
        text_count=text_count,
        status=status,
        detail=detail,
        ordered_types=ordered_types,
        message_ids=[row.message_id for row in ordered_rows],
    )


def check_posts(rows: list[MessageRow]) -> list[PostCheckResult]:
    grouped: dict[str, list[MessageRow]] = defaultdict(list)
    for row in rows:
        grouped[build_post_key(row)].append(row)
    return [classify_post(group_rows) for _, group_rows in sorted(grouped.items(), key=lambda item: item[0])]


def print_summary(results: list[PostCheckResult]) -> None:
    counts = Counter(result.status for result in results)
    print('总结信息(Summary)')
    print(f'  总post数(total_posts): {len(results)}')
    for status in ['complete', 'misordered', 'missing', 'duplicate_send', 'unknown']:
        print(f'  {STATUS_LABELS[status]}: {counts.get(status, 0)}')


def should_print_result(result: PostCheckResult, args: argparse.Namespace) -> bool:
    if args.status and result.status != args.status:
        return False
    if args.show_complete:
        return True
    return result.status != 'complete'


def print_result(result: PostCheckResult) -> None:
    print('-' * 80)
    print(f'状态(status): {STATUS_LABELS.get(result.status, result.status)}')
    print(f'说明(detail): {result.detail}')
    print(f'链接(url): {result.url}')
    print(f'idstr: {result.idstr}')
    print(f'mblogid: {result.mblogid}')
    print(f'用户ID(userid): {result.userid}')
    print(f'用户名(username): {result.username}')
    print(f'消息总数(total_messages): {result.total_messages}')
    print(f'媒体消息数(media_count): {result.media_count}')
    print(f'文字消息数(text_count): {result.text_count}')
    print(f'发送顺序(ordered_types): {" -> ".join(result.ordered_types)}')
    print(f'消息ID(message_ids): {", ".join(str(item) for item in result.message_ids)}')


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rows = fetch_rows(args)
    results = check_posts(rows)

    if args.summary_only:
        print_summary(results)
        return

    filtered_results = [result for result in results if should_print_result(result, args)]
    if args.limit >= 0:
        filtered_results = filtered_results[:args.limit]

    if not filtered_results:
        print('没有匹配到需要输出的 post。')
        print_summary(results)
        return

    for result in filtered_results:
        print_result(result)

    print('-' * 80)
    print_summary(results)


if __name__ == '__main__':
    main()
