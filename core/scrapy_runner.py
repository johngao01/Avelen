from typing import Callable, Any
import traceback
import argparse

from core.downloader import Downloader
from core.database import get_filtered_followings, get_send_url
from core.models import BasePost
from core.sender_dispatcher import send_post_payload_to_telegram
from core.settings import (
    disable_download_progress,
    enable_download_progress,
    enable_no_send_mode,
    is_no_send_mode,
)
from core.utils import download_log, log_error, rate_control


def build_post_summary(post: BasePost) -> dict[str, Any]:
    return {
        'platform': post.platform,
        'username': post.username,
        'nickname': post.nickname,
        'url': post.url,
        'userid': post.userid,
        'idstr': post.idstr,
        'mblogid': post.mblogid,
        'create_time': post.create_time.strftime('%Y-%m-%d %H:%M:%S'),
        'text_raw': post.text_raw,
    }


def build_download_summary(files: list[Any]) -> dict[str, Any]:
    return {
        'file_count': len(files),
        'results': [{
            'url': result.task.url,
            'path': result.path,
            'ok': result.ok,
            'http_status': result.status_code,
            'size': result.size,
            'exists': result.exists,
            'skipped': result.skipped,
            'error': result.error,
            'media_type': result.task.media_type,
            'dispatch_file': result.to_dispatch_file(),
        } for result in files],
    }


def send_post_to_telegram(post: BasePost, logger):
    """下载单条作品媒体，并返回统一的 Telegram 处理结果。

    职责：
    - 调用 `Downloader` 下载当前作品对应的全部媒体
    - 让平台对象把下载结果整理成发送 payload
    - 在 `--no-send` 模式下返回成功但不实际发送
    - 在正常模式下把 payload 交给 Telegram 发送层

    返回值始终是 `dict`，核心字段如下：
    - `ok`: 当前处理是否成功
    - `error`: 失败原因，成功时为 `None`
    - `mode`: `prepare` / `no-send` / `telegram`
    - `post`: 当前作品摘要
    - `download`: 下载结果摘要
    - `persisted`: 是否已将 Telegram 消息写入数据库
    - `messages`: 已落库的消息记录列表
    - `telegram`: Telegram 发送过程详情
    """
    downloader = Downloader(logger=logger)
    files = downloader.download(post)
    download_summary = build_download_summary(files)
    post_summary = build_post_summary(post)
    post_data = post.to_dispatch_data(files)
    if not post_data:
        return {
            'ok': False,
            'error': '构造发送数据失败',
            'mode': 'prepare',
            'post': post_summary,
            'download': download_summary,
            'messages': [],
            'telegram': {
                'chat_id': None,
                'event_count': 0,
                'message_count': 0,
                'events': [],
                'messages': [],
                'persisted_messages': [],
            },
        }
    if is_no_send_mode():
        logger.info(f"no-send 模式，跳过 Telegram 发送：{post.url}")
        return {
            'ok': True,
            'error': None,
            'mode': 'no-send',
            'post': post_summary,
            'download': download_summary,
            'persisted': False,
            'messages': [],
            'telegram': {
                'skipped': True,
                'chat_id': None,
                'event_count': 0,
                'message_count': 0,
                'events': [],
                'messages': [],
                'persisted_messages': [],
            },
        }
    result = send_post_payload_to_telegram(post_data)
    if isinstance(result, dict):
        result.setdefault('mode', 'telegram')
        result.setdefault('post', post_summary)
        result.setdefault('download', download_summary)
    return result


def handle_dispatch_result(result, logger, url: str, on_success_update=None, on_failure_update=None) -> str:
    if isinstance(result, dict) and result.get('ok'):
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
    error_text = result.get('error') if isinstance(result, dict) else result
    log_error(url, error_text)
    logger.error(f"处理 {url} 失败")
    return 'failure'


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
