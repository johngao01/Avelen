from dataclasses import dataclass
from typing import Callable, Any
import traceback
import argparse

from core.downloader import Downloader
from core.database import get_filtered_followings
from core.post import BasePost
from core.settings import enable_no_send_mode, is_no_send_mode
from core.utils import download_log, log_error, rate_control, request_webhook


@dataclass(slots=True)
class PostProcessSummary:
    total: int = 0
    success: int = 0
    failure: int = 0
    skipped: int = 0
    latest_post: Any | None = None


def dispatch_post(post: BasePost, logger):
    downloader = Downloader(logger=logger)
    post_data = post.to_dispatch_data(downloader.download_post(post))
    if not post_data:
        return '获取失败'
    return request_webhook('/main', post_data, logger)


def handle_dispatch_result(result, logger, url: str, on_success_update=None, on_failure_update=None) -> str:
    if getattr(result, 'status_code', None) == 200:
        if not is_no_send_mode():
            download_log(result)
            rate_control(result, logger)
            if on_success_update:
                on_success_update()
        return 'success'
    if isinstance(result, str) and 'skip' in result:
        return 'skip'
    if on_failure_update:
        on_failure_update()
    error_text = getattr(result, 'status_code', result)
    log_error(url, error_text)
    logger.error(f"处理 {url} 失败")
    return 'failure'


def update_after_batch(on_update=None):
    if not is_no_send_mode() and on_update:
        on_update()


def run_posts(posts: list[Any],
              dispatch_one: Callable[[Any], Any],
              logger,
              *,
              describe_post: Callable[[Any], str] | None = None,
              url_of: Callable[[Any], str] | None = None) -> PostProcessSummary:
    ordered_posts = list(posts)
    summary = PostProcessSummary(
        total=len(ordered_posts),
        latest_post=ordered_posts[-1] if ordered_posts else None,
    )
    for index, post in enumerate(ordered_posts, start=1):
        post_text = describe_post(post) if describe_post else str(post)
        logger.info(f"{index}/{summary.total}\t{post_text}")
        post_url = url_of(post) if url_of else getattr(post, 'url', post_text)
        status = handle_dispatch_result(dispatch_one(post), logger, post_url)
        if status == 'success':
            summary.success += 1
        elif status == 'skip':
            summary.skipped += 1
        else:
            summary.failure += 1
    return summary


def run_followings(all_followings: list[Any],
                   build_following: Callable[[Any], Any],
                   run_one: Callable[[Any], None],
                   logger,
                   finished_message: str = "本次任务结束\n"):
    """
    统一抓取入口：
    - build_following: 将数据库行转换为 Following/Profile 对象
    - run_one: 执行单账号抓取和处理
    - logger: 统一异常与结束日志输出
    """
    following_count = len(all_followings)
    for i, raw_data in enumerate(all_followings, start=1):
        following = build_following(raw_data)
        try:
            logger.info(f"{i}/{following_count}\t{following.start_msg}")
            run_one(following)
        except Exception:
            logger.info(traceback.format_exc())
        finally:
            if following.end_msg:
                logger.info(following.end_msg)
    if finished_message:
        logger.info(finished_message)


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
    parser.add_argument('--local-json', action='store_true', help='从本地 json 目录读取数据，而不是实时抓取')
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
                       configure_parser: Callable[[argparse.ArgumentParser], None] | None = None,
                       argv=None):
    """Build parser, parse args, apply runtime flags, and select followings in one call."""
    parser = build_common_cli_parser(default_valid=default_valid)
    if configure_parser:
        configure_parser(parser)
    args = parser.parse_args(argv)
    if getattr(args, 'no_send', False):
        enable_no_send_mode()
    return args, select_followings(platform, args)
