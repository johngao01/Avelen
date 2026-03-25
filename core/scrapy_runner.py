import argparse
import sys
import traceback
from typing import Callable, Any

from core.downloader import Downloader
from core.database import get_filtered_followings, get_sent_post
from core.models import BasePost, RunOptions
from core.sender_dispatcher import send_post_payload_to_telegram
from core.utils import download_log, log_error, rate_control


def send_post_to_telegram(
        post: BasePost,
        logger,
        *,
        options: RunOptions | None = None,
):
    """下载单条作品媒体，并返回统一处理结果。

    职责：
    - 调用 `Downloader` 下载当前作品对应的全部媒体
    - 在 `--no-send` 模式下返回成功但不实际发送
    - 在正常模式下把下载结果交给 Telegram 发送层

    返回值始终是 `dict`，仅保留后续流程真正依赖的字段：
    - `ok`: 当前处理是否成功
    - `error`: 失败原因，成功时为 `None`
    - `messages`: 已落库的消息记录列表
    """
    if options is None:
        options = RunOptions()

    downloader = Downloader(logger=logger, show_progress=options.download_progress)
    payload = downloader.download(post)
    download_ok = bool(payload.get('ok'))
    if not download_ok:
        return {
            'ok': False,
            'error': '所有文件未全部下载完成',
            'messages': [],
        }
    if options.no_send:
        return {
            'ok': True,
            'error': None,
            'messages': [],
        }
    result = send_post_payload_to_telegram(payload)
    return result


def handle_dispatch_result(
        result,
        logger,
        url: str,
        on_success_update=None,
        on_failure_update=None,
        *,
        options: RunOptions | None = None,
) -> str:
    if options is None:
        options = RunOptions()

    if isinstance(result, dict) and result.get('ok'):
        if not options.no_send:
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
            logger.info(f"{i}/{following_count} {following.start_msg}")
            run_one(following)
        except Exception:
            logger.info(traceback.format_exc())
        finally:
            if following.end_msg:
                logger.info(following.end_msg)
    if finished_message:
        logger.info(finished_message)


def build_common_cli_parser():
    """构建各平台共用命令行参数。"""
    parser = argparse.ArgumentParser(description='Scrapy runner options')
    parser.add_argument('--valid', nargs='+', type=int, default=list((1,)), choices=[0, 1, 2],
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


def build_run_options(args: argparse.Namespace) -> RunOptions:
    """从 CLI 参数中提取执行链路需要的运行时参数。"""
    return RunOptions(
        use_local_json=getattr(args, 'local_json', False),
        no_send=getattr(args, 'no_send', False),
        download_progress=getattr(args, 'download_progress', True),
    )


def run_platform_main(platform: str,
                      logger,
                      build_following: Callable[[Any], Any],
                      run_one: Callable[[Any, set[str], RunOptions], None]):
    """运行平台命令行入口的公共壳层。"""
    parser = build_common_cli_parser()
    argv = sys.argv[1:]
    if argv and argv[0] == platform:
        argv = argv[1:]
    args = parser.parse_args(argv)
    all_followings = select_followings(platform, args)
    options = build_run_options(args)
    sent_post = set(get_sent_post(platform))
    run_followings(
        all_followings,
        build_following=build_following,
        run_one=lambda following: run_one(following, sent_post, options),
        logger=logger,
    )
    return args, all_followings
