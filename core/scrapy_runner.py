from typing import Callable, Iterable, Any
import traceback
import argparse

from core.database import get_filtered_followings
from core.settings import enable_no_send_mode


def run_followings(all_followings: Iterable[Any], build_following: Callable[[Any], Any], run_one: Callable[[Any], None], logger, finished_message: str = "本次任务结束\n\n"):
    """
    统一抓取入口：
    - build_following: 将数据库行转换为 Following/Profile 对象
    - run_one: 执行单账号抓取和处理
    - logger: 统一异常与结束日志输出
    """
    try:
        for raw in all_followings:
            run_one(build_following(raw))
        logger.info(finished_message)
    except Exception:
        logger.info(traceback.format_exc())


def build_common_cli_parser(default_valid=(1,)):
    """构建各平台共用命令行参数。"""
    parser = argparse.ArgumentParser(description='Scrapy runner options')
    parser.add_argument('--valid', nargs='+', type=int, default=list(default_valid), choices=[0, 1, 2],
                        help='关注类型，可多选：0取消关注 1特别关注 2普通关注，默认 1')
    parser.add_argument('--user-id', action='append', dest='user_ids', default=[],
                        help='按 user.userid 精确筛选，可重复传参')
    parser.add_argument('--username', action='append', dest='usernames', default=[],
                        help='按 user.username 精确筛选，可重复传参')
    parser.add_argument('--latest-time-start', default=None,
                        help='筛选 latest_time >= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--latest-time-end', default=None,
                        help='筛选 latest_time <= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--scrapy-time-start', default=None,
                        help='筛选 scrapy_time >= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--scrapy-time-end', default=None,
                        help='筛选 scrapy_time <= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--no-send', action='store_true',
                        help='仅爬取和下载，不发送 Telegram，也不更新用户 latest_time')
    return parser


def select_followings(platform: str, args):
    """根据命令行参数统一从 user 表筛选关注列表。"""
    return get_filtered_followings(
        platform=platform,
        valid_list=args.valid,
        user_ids=args.user_ids,
        usernames=args.usernames,
        latest_time_start=args.latest_time_start,
        latest_time_end=args.latest_time_end,
        scrapy_time_start=args.scrapy_time_start,
        scrapy_time_end=args.scrapy_time_end,
    )


def prepare_followings(platform: str, default_valid=(1,),
                      configure_parser: Callable[[argparse.ArgumentParser], None] | None = None):
    """Build parser, parse args, apply runtime flags, and select followings in one call."""
    parser = build_common_cli_parser(default_valid=default_valid)
    if configure_parser:
        configure_parser(parser)
    args = parser.parse_args()
    if getattr(args, 'no_send', False):
        enable_no_send_mode()
    return args, select_followings(platform, args)


