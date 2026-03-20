from dataclasses import dataclass
from typing import Callable, Any
import traceback
import argparse

from core.downloader import Downloader
from core.database import get_filtered_followings, get_send_url, update_db
from core.models import BasePost
from core.sender_dispatcher import dispatch_post_data
from core.settings import (
    disable_download_progress,
    enable_download_progress,
    enable_no_send_mode,
    is_no_send_mode,
)
from core.utils import download_log, log_error, rate_control


@dataclass(slots=True)
class PostProcessSummary:
    total: int = 0
    success: int = 0
    failure: int = 0
    skipped: int = 0
    latest_post: Any | None = None


def dispatch_post(post: BasePost, logger):
    downloader = Downloader(logger=logger)
    files = downloader.download(post)
    post_data = post.to_dispatch_data(files)
    if not post_data:
        return '获取失败'
    return dispatch_post_data(post_data)


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
              logger) -> PostProcessSummary:
    ordered_posts = list(posts)
    summary = PostProcessSummary(
        total=len(ordered_posts),
        latest_post=ordered_posts[-1] if ordered_posts else None,
    )
    for index, post in enumerate(ordered_posts, start=1):
        should_process, start_message = post.start()
        logger.info(f"{index}/{summary.total}\t{start_message}")
        if not should_process:
            summary.skipped += 1
            continue
        status = handle_dispatch_result(dispatch_one(post), logger, post.url)
        if status == 'success':
            summary.success += 1
        elif status == 'skip':
            summary.skipped += 1
        else:
            summary.failure += 1
    return summary


def filter_new_posts(posts: list[Any],
                     sent_urls: set[str],
                     latest_time,
                     *,
                     exclude_equal: bool = True,
                     should_sort: bool = True,
                     skip_post: Callable[[Any], bool] | None = None) -> list[Any]:
    """按公共规则过滤真正需要处理的新内容。

    过滤逻辑不直接并入 `get_post_from_api()`，因为本地 JSON 回放模式也要复用同一套规则。
    平台自己的 API 抓取阶段仍然可以做“提前终止分页”之类的优化，但最终去重与排序放在这里统一。
    """
    new_posts = []
    for post in posts:
        if post.url in sent_urls:
            continue
        if exclude_equal:
            if post.create_time <= latest_time:
                continue
        elif post.create_time < latest_time:
            continue
        if skip_post and skip_post(post):
            continue
        new_posts.append(post)
    if should_sort:
        new_posts.sort(key=lambda x: x.create_time)
    return new_posts


def get_post_latest_time_str(post: Any) -> str:
    """返回写回数据库时使用的 latest_time 字符串。"""
    create_time_str = getattr(post, 'create_time_str', None)
    if isinstance(create_time_str, str):
        return create_time_str
    return post.create_time.strftime('%Y-%m-%d %H:%M:%S')


def start_platform_scraping(scraper: Any,
                            sent_urls: set[str],
                            *,
                            use_local_json: bool,
                            logger,
                            content_name: str,
                            show_time_range: bool = True,
                            dispatch_one: Callable[[Any], Any] | None = None) -> None:
    """执行平台实例的通用抓取、过滤、发送和回写流程。"""
    if use_local_json:
        scraper.get_post_from_local()
    else:
        scraper.get_post_from_api()

    new_posts = scraper.filter_new_post(sent_urls)
    username = scraper.scraping.username
    if not new_posts:
        scraper.scraping.end_msg = f'{username} 处理结束，没有新{content_name}\n'
        return

    if show_time_range:
        logger.info(
            f'{username} 有 {len(new_posts)} 个新{content_name}。 '
            f'{new_posts[0].create_time}  {new_posts[-1].create_time}'
        )
    else:
        logger.info(f'{username} 有 {len(new_posts)} 个新{content_name}')

    if dispatch_one is None:
        dispatch_one = lambda post: dispatch_post(post, logger)

    summary = run_posts(
        new_posts,
        dispatch_one=dispatch_one,
        logger=logger,
    )
    update_after_batch(lambda: update_db(
        scraper.scraping.userid,
        scraper.scraping.username,
        get_post_latest_time_str(new_posts[-1]),
    ))
    scraper.scraping.end_msg = (
        f'{username} 处理结束，'
        f'新{content_name} {summary.total} 个，'
        f'跳过 {summary.skipped} 个，'
        f'成功 {summary.success} 个，失败 {summary.failure} 个\n'
    )


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
    parser.add_argument('-dp', '--download-progress', action=argparse.BooleanOptionalAction, default=True,
                        help='是否显示下载进度条，默认启用')
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
    if getattr(args, 'download_progress', True):
        enable_download_progress()
    else:
        disable_download_progress()
    return args, select_followings(platform, args)


def run_platform_main(platform: str,
                      logger,
                      build_following: Callable[[Any], Any],
                      run_one: Callable[[Any, set[str], argparse.Namespace], None],
                      *,
                      default_valid=(1,),
                      configure_parser: Callable[[argparse.ArgumentParser], None] | None = None,
                      argv=None):
    """运行平台命令行入口的公共壳层。"""
    args, all_followings = prepare_followings(
        platform,
        default_valid=default_valid,
        configure_parser=configure_parser,
        argv=argv,
    )
    sent_urls = set(get_send_url(platform))
    run_followings(
        all_followings,
        build_following=build_following,
        run_one=lambda following: run_one(following, sent_urls, args),
        logger=logger,
    )
    return args, all_followings
