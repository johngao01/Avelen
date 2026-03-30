import argparse
import sys
import traceback
from datetime import datetime
from typing import Callable, Any

from core.downloader import Downloader
from core.database import get_filtered_following_rows, get_filtered_followings, get_sent_post, normalize_sort_option
from core.models import BasePost, CookieExpiredError, DEFAULT_LATEST_TIME, RunOptions
from core.settings import BILIBILI_CONFIG, DOUYIN_CONFIG, INSTAGRAM_CONFIG, WEIBO_CONFIG
from core.sender_dispatcher import send_post_payload_to_telegram
from core.utils import download_log, log_error, rate_control
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()
VALID_LABELS = {
    0: '取关',
    1: '特关',
    2: '普关',
    -1: '停更',
    -2: '失效',
}


def argparse_sort_option(value: str) -> str:
    """在 argparse 层提前校验并标准化排序参数。"""
    try:
        return normalize_sort_option(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def argparse_latest_time_override(value: str) -> datetime:
    """解析 `set-latest-time` 参数；空值时回退到默认最早时间。"""
    if value == '':
        return DEFAULT_LATEST_TIME
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise argparse.ArgumentTypeError('时间格式无效，应为 YYYY-MM-DD HH:MM:SS') from exc


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
    post_data = downloader.download(post)
    download_ok = post_data.ok
    if not download_ok:
        return {
            'ok': False,
            'error': '所有文件未全部下载完成',
            'post_data': post_data,
            'messages': [],
        }
    if options.no_send or len(post_data.files) == 0:
        return {
            'ok': True,
            'error': None,
            'post_data': post_data,
            'messages': [],
        }

    result = send_post_payload_to_telegram(post_data)
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
        except CookieExpiredError as exc:
            error_message = (
                f"Cookie 已失效，程序退出\n"
                f"账号: {following.username} ({following.userid})\n"
                f"错误: {exc}"
            )
            logger.error(error_message)
            raise SystemExit(1) from exc
        except Exception:
            logger.error(traceback.format_exc())
        finally:
            if following.end_msg:
                logger.info(following.end_msg)
    if finished_message:
        logger.info(finished_message)


def build_common_cli_parser():
    """构建各平台共用命令行参数。"""
    parser = argparse.ArgumentParser(description='Scrapy runner options')
    parser.add_argument('-v', '--valid', nargs='+', type=int, default=list((1,)), choices=[-2, -1, 0, 1, 2],
                        help='关注类型，可多选：-2这个用户被平台删了 -1不再关注 0取消关注 1特别关注 2普通关注，默认 1')
    parser.add_argument('-id', '--uid', '--user-id', action='append', dest='user_ids', default=[],
                        help='按 user.userid 精确筛选，可重复传参')
    parser.add_argument('--name', '--username', action='append', dest='usernames', default=[],
                        help='按 user.username 精确筛选，可重复传参')
    parser.add_argument('-rn', '--rename', dest='username_like', default=None,
                        help='按 user.username 模糊筛选，支持输入部分用户名')
    parser.add_argument('--lts', '--latest-time-start', dest='latest_time_start', default=None,
                        help='筛选 latest_time >= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--lte', '--latest-time-end', dest='latest_time_end', default=None,
                        help='筛选 latest_time <= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--sts', '--scrapy-time-start', dest='scrapy_time_start', default=None,
                        help='筛选 scrapy_time >= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--ste', '--scrapy-time-end', dest='scrapy_time_end', default=None,
                        help='筛选 scrapy_time <= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('-s', '--sort', dest='sort_option', type=argparse_sort_option, default='scrapy_time:desc',
                        help='排序字段[:asc|desc]，默认 scrapy_time:desc')
    parser.add_argument('-slt', '--set-latest-time', dest='set_latest_time', nargs='?', default=None,
                        const=DEFAULT_LATEST_TIME, type=argparse_latest_time_override,
                        help='覆盖所有用户 latest_time；不传值或传空值时使用 2000-12-12 12:12:12')
    parser.add_argument('-n', '--no-send', action='store_true',
                        help='仅爬取和下载，不发送 Telegram，也不更新用户 latest_time')
    parser.add_argument('-p', '--progress', '--download-progress', dest='download_progress',
                        action='store_false', default=True, help='是否显示下载进度条，默认启用')
    parser.add_argument('-j', '--json', '--local-json', dest='local_json', action='store_true',
                        help='从本地 json 目录读取数据，而不是实时抓取')
    parser.add_argument('-l', '--list', dest='show', action='store_true',
                        help='只展示筛选后的 user 表记录，不执行爬取和发送')
    return parser


def build_following_filters(args) -> dict[str, Any]:
    """把 CLI 参数整理成统一的数据库筛选参数。"""
    return {
        'valid_list': args.valid,
        'user_ids': args.user_ids,
        'usernames': args.usernames,
        'username_like': args.username_like,
        'latest_time_start': args.latest_time_start,
        'latest_time_end': args.latest_time_end,
        'scrapy_time_start': args.scrapy_time_start,
        'scrapy_time_end': args.scrapy_time_end,
        'sort_option': args.sort_option,
    }


def apply_latest_time_override(rows, override_latest_time):
    """统一覆盖筛选结果中的 latest_time，便于强制全量抓取。"""
    if override_latest_time is None:
        return rows

    updated_rows = []
    for row in rows:
        row_values = list(row)
        if len(row_values) == 3:
            row_values[2] = override_latest_time
        elif len(row_values) >= 5:
            row_values[4] = override_latest_time
        updated_rows.append(tuple(row_values))
    return updated_rows


def select_followings(platform: str, args):
    """根据命令行参数统一从 user 表筛选关注列表。"""
    rows = get_filtered_followings(
        platform=platform,
        **build_following_filters(args),
    )
    return apply_latest_time_override(rows, args.set_latest_time)


def build_run_options(args: argparse.Namespace) -> RunOptions:
    """从 CLI 参数中提取执行链路需要的运行时参数。"""
    return RunOptions(
        use_local_json=getattr(args, 'local_json', False),
        no_send=getattr(args, 'no_send', False),
        download_progress=getattr(args, 'download_progress', True),
    )


def select_following_rows(platform: str | None, args):
    """根据命令行参数读取用于展示的 user 表记录。

    `platform=None` 时表示跨平台读取，供主入口自动分发和 `--show` 使用。
    """
    rows = get_filtered_following_rows(
        platform=platform,
        **build_following_filters(args),
    )
    return apply_latest_time_override(rows, args.set_latest_time)


def format_table_value(value) -> str:
    """把数据库值转换成更适合控制台表格展示的字符串。"""
    if value is None or value == '':
        return '-'
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def build_profile_url(platform: str, userid: str) -> str | None:
    """根据平台和 userid 生成可点击的主页链接。"""
    if not userid:
        return None
    if platform == 'weibo':
        return f"{WEIBO_CONFIG['base_url']}/u/{userid}"
    if platform == 'douyin':
        return f"{DOUYIN_CONFIG['user_url']}{userid}"
    if platform == 'bilibili':
        return f"{BILIBILI_CONFIG['space_url']}/{userid}/dynamic"
    if platform == 'instagram':
        return f"{INSTAGRAM_CONFIG['base_url']}/{userid}"
    return None


def build_link_text(label: str, url: str | None) -> Text:
    """为支持 OSC 8 的终端生成超链接文本。"""
    text = Text(label)
    if url:
        text.stylize(f"link {url}")
        text.stylize("underline blue")
    return text


def render_followings_table(platform: str | None, rows, *, show_platform: bool = False,
                            title: str | None = None) -> None:
    """把筛选后的 user 记录渲染成控制台表格。

    - 单平台模式：隐藏平台列
    - 跨平台模式：显示平台列，便于确认自动分发结果
    """
    platform_label = platform or '全部平台'
    if not rows:
        console.print(f"[yellow]{platform_label} 没有符合条件的用户[/yellow]")
        return

    table = Table(
        title=title or f"{platform_label} 用户筛选结果（共 {len(rows)} 个）",
        header_style='bold cyan',
        box=box.ASCII2,
        show_lines=True,
    )
    table.add_column('序号', justify='right', style='dim', no_wrap=True)
    table.add_column('用户ID', style='green')
    table.add_column('用户名', style='magenta')
    if show_platform:
        table.add_column('平台', style='blue')
    table.add_column('关注类型', style='yellow')
    table.add_column('最新作品时间', style='white', no_wrap=True)
    table.add_column('最后爬取时间', style='white', no_wrap=True)

    for index, row in enumerate(rows, start=1):
        userid, username, row_platform, valid, latest_time, scrapy_time = row
        userid_text = format_table_value(userid)
        username_text = format_table_value(username)
        profile_url = build_profile_url(row_platform, str(userid))
        table.add_row(
            str(index),
            build_link_text(userid_text, profile_url),
            build_link_text(username_text, profile_url),
            *([format_table_value(row_platform)] if show_platform else []),
            VALID_LABELS.get(valid, format_table_value(valid)),
            format_table_value(latest_time),
            format_table_value(scrapy_time),
        )

    console.print(table)


def build_args_log_summary(args: argparse.Namespace) -> str:
    """把当前 CLI 参数整理成适合启动日志的简短摘要。"""
    summary = [
        f"valid={args.valid}",
        f"sort={args.sort_option}",
    ]
    if args.user_ids:
        summary.append(f"user_ids={args.user_ids}")
    if args.usernames:
        summary.append(f"usernames={args.usernames}")
    if args.username_like:
        summary.append(f"username_like={args.username_like}")
    if args.latest_time_start:
        summary.append(f"latest_time_start={args.latest_time_start}")
    if args.latest_time_end:
        summary.append(f"latest_time_end={args.latest_time_end}")
    if args.scrapy_time_start:
        summary.append(f"scrapy_time_start={args.scrapy_time_start}")
    if args.scrapy_time_end:
        summary.append(f"scrapy_time_end={args.scrapy_time_end}")
    if args.set_latest_time is not None:
        summary.append(f"set_latest_time={format_table_value(args.set_latest_time)}")
    if args.local_json:
        summary.append("local_json=True")
    if args.no_send:
        summary.append("no_send=True")
    if not args.download_progress:
        summary.append("download_progress=False")
    if args.show:
        summary.append("show=True")
    return ', '.join(summary)


def run_platform_main(platform: str,
                      logger,
                      build_following: Callable[[Any], Any],
                      run_one: Callable[[Any, set[str], RunOptions], None]):
    """运行平台命令行入口的公共壳层。

    当传入 `--show` 时，只展示筛选结果，不进入抓取链路。
    """
    parser = build_common_cli_parser()
    argv = sys.argv[1:]
    if argv and argv[0] == platform:
        argv = argv[1:]
    args = parser.parse_args(argv)
    logger.info(f"{platform} 任务启动")
    logger.info(f"{platform} 参数: {build_args_log_summary(args)}")
    if args.show:
        logger.info(f"{platform} 开始筛选用户（show 模式）")
        rows = select_following_rows(platform, args)
        logger.info(f"{platform} show 模式共筛到 {len(rows)} 个用户")
        render_followings_table(platform, rows)
        return args, rows
    logger.info(f"{platform} 开始筛选用户")
    all_followings = select_followings(platform, args)
    logger.info(f"{platform} 筛选完成，共 {len(all_followings)} 个用户")
    if not all_followings:
        logger.info(f"{platform} 没有符合条件的用户，本次任务结束")
        return args, all_followings
    options = build_run_options(args)
    logger.info(
        f"{platform} 运行模式: "
        f"local_json={options.use_local_json}, "
        f"no_send={options.no_send}, "
        f"download_progress={options.download_progress}"
    )
    sent_post = set(get_sent_post(platform))
    logger.info(f"{platform} 已加载 {len(sent_post)} 条历史已发送记录")
    logger.info(f"{platform} 开始执行抓取流程")
    run_followings(
        all_followings,
        build_following=build_following,
        run_one=lambda following: run_one(following, sent_post, options),
        logger=logger,
    )
    return args, all_followings
