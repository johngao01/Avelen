import argparse
import configparser
import random
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from typing import Callable, Any

from core.downloader import Downloader
from core.database import get_filtered_following_rows, get_filtered_followings, get_sent_post, normalize_sort_option
from core.models import BasePost, CookieExpiredError, DEFAULT_LATEST_TIME, RunContext, RunOptions, RunStats
from core.settings import BILIBILI_CONFIG, DOUYIN_CONFIG, INSTAGRAM_CONFIG, PROJECT_ROOT, WEIBO_CONFIG
from core.sender_dispatcher import send_post_payload_to_telegram
from core.utils import download_log, log_error, rate_control
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()
VALID_LABELS = {
    0: '很久没更新',
    1: '普通关注',
    2: '特别关注',
    -1: '不喜欢了',
    -2: '账号失效',
}
DEFAULT_CONFIG_PATH = PROJECT_ROOT / 'config' / 'avelen.conf'
COMMON_CLI_DEFAULTS = {
    'config': str(DEFAULT_CONFIG_PATH),
    'ignore_config': False,
    'valid': [2],
    'user_ids': [],
    'usernames': [],
    'username_like': None,
    'latest_time_start': None,
    'latest_time_end': None,
    'scrapy_time_start': None,
    'scrapy_time_end': None,
    'sort_option': 'scrapy_time:desc',
    'set_latest_time': None,
    'no_send': False,
    'send_on_download_failure': False,
    'download_progress': True,
    'local_json': False,
    'show': False,
    'rate_limit': None,
    'platform': None,
}
CONFIG_KEY_ALIASES = {
    'config': 'config',
    'valid': 'valid',
    'uid': 'user_ids',
    'user_id': 'user_ids',
    'user_ids': 'user_ids',
    'name': 'usernames',
    'username': 'usernames',
    'usernames': 'usernames',
    'rename': 'username_like',
    'username_like': 'username_like',
    'latest_time_start': 'latest_time_start',
    'latest_time_end': 'latest_time_end',
    'scrapy_time_start': 'scrapy_time_start',
    'scrapy_time_end': 'scrapy_time_end',
    'sort': 'sort_option',
    'sort_option': 'sort_option',
    'set_latest_time': 'set_latest_time',
    'no_send': 'no_send',
    'send_on_download_failure': 'send_on_download_failure',
    'download_progress': 'download_progress',
    'local_json': 'local_json',
    'show': 'show',
    'list': 'show',
    'rate_limit': 'rate_limit',
}


def _split_config_list(value: str) -> list[str]:
    parts = [item.strip() for item in value.replace(',', '\n').splitlines()]
    return [item for item in parts if item]


def _parse_config_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError(f'无效的布尔值: {value}')


def _resolve_config_key(raw_key: str) -> str | None:
    return CONFIG_KEY_ALIASES.get(raw_key.strip().lower().replace('-', '_'))


def _convert_config_value(dest: str, raw_value: str):
    value = raw_value.strip()
    if dest == 'valid':
        return [int(item) for item in _split_config_list(value)]
    if dest in {'user_ids', 'usernames'}:
        return _split_config_list(value)
    if dest == 'sort_option':
        return argparse_sort_option(value)
    if dest == 'set_latest_time':
        return argparse_latest_time_override(value)
    if dest in {'no_send', 'send_on_download_failure', 'download_progress', 'local_json', 'show'}:
        return _parse_config_bool(value)
    if dest == 'rate_limit':
        return _split_config_list(value)
    if dest == 'config':
        return value
    return value or None


def _load_cli_config(config_path: str | Path, sections: list[str]) -> dict[str, Any]:
    path = _resolve_config_path(config_path)
    if not path.exists():
        return {}

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding='utf-8')
    loaded: dict[str, Any] = {}
    for section in sections:
        if not parser.has_section(section):
            continue
        for raw_key, raw_value in parser.items(section):
            dest = _resolve_config_key(raw_key)
            if not dest:
                continue
            try:
                loaded[dest] = _convert_config_value(dest, raw_value)
            except (ValueError, argparse.ArgumentTypeError) as exc:
                raise ValueError(f'{path} [{section}] {raw_key} 配置无效: {exc}') from exc
    loaded['config'] = str(path)
    return loaded


def _resolve_config_path(config_path: str | Path) -> Path:
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def _build_default_args() -> argparse.Namespace:
    return argparse.Namespace(**{
        key: list(value) if isinstance(value, list) else value
        for key, value in COMMON_CLI_DEFAULTS.items()
    })


def _preparse_common_cli(argv: list[str]) -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument('-c', '--config', dest='config')
    pre_parser.add_argument('--ignore-config', action='store_true')
    return pre_parser.parse_known_args(argv)[0]


def _guess_entry_sections(
        entry_name: str,
        *,
        include_position_platform: bool,
        platform_name: str | None = None,
) -> list[str]:
    sections = ['default']
    if entry_name != 'default':
        sections.append(entry_name)
    if include_position_platform and platform_name:
        sections.append(platform_name.lower())
    return list(dict.fromkeys(sections))


def parse_cli_args(
        parser: argparse.ArgumentParser,
        argv: list[str],
        *,
        entry_name: str,
        include_position_platform: bool = False,
) -> argparse.Namespace:
    defaults = vars(_build_default_args())
    cli_probe = _preparse_common_cli(argv)
    cli_values = vars(parser.parse_args(argv))
    config_path = cli_probe.config or defaults['config']
    sections = _guess_entry_sections(
        entry_name,
        include_position_platform=include_position_platform,
        platform_name=cli_values.get('platform'),
    )

    config_values: dict[str, Any] = {}
    if not cli_probe.ignore_config:
        try:
            config_values = _load_cli_config(config_path, sections)
        except ValueError as exc:
            parser.error(str(exc))

    merged = defaults | config_values | cli_values
    merged['config'] = str(_resolve_config_path(merged['config']))
    return argparse.Namespace(**merged)


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


def argparse_rate_limit(values: list[str]) -> tuple[int, int]:
    """解析 rate-limit 参数，支持固定值或区间值。"""
    if not values:
        raise argparse.ArgumentTypeError('rate-limit 至少需要 1 个参数')
    if len(values) > 2:
        raise argparse.ArgumentTypeError('rate-limit 仅支持 1 个或 2 个参数')
    try:
        seconds = [int(item) for item in values]
    except ValueError as exc:
        raise argparse.ArgumentTypeError('rate-limit 必须是整数秒') from exc
    if any(item < 0 for item in seconds):
        raise argparse.ArgumentTypeError('rate-limit 不能为负数')
    if len(seconds) == 1:
        return seconds[0], seconds[0]
    low, high = sorted(seconds)
    return low, high


def send_post_to_telegram(
        post: BasePost,
        logger,
        *,
        context: RunContext
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
    options = context.options
    downloader = Downloader(logger=logger, show_progress=options.download_progress)
    post_data = downloader.download(post)
    download_ok = post_data.ok
    if not download_ok and not options.send_on_download_failure:
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
        context: RunContext,
) -> str:
    options = context.options
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
                   context: RunContext,
                   finished_message: str = "本次任务结束\n"):
    """
    统一抓取入口：
    - build_following: 将数据库行转换为 Following/Profile 对象
    - run_one: 执行单账号抓取和处理
    - logger: 统一异常与结束日志输出
    """
    following_count = len(all_followings)
    options = context.options
    wait_min = max(0, getattr(options, 'scrapy_wait_min_seconds'))
    wait_max = max(0, getattr(options, 'scrapy_wait_max_seconds'))
    if wait_min > wait_max:
        wait_min, wait_max = wait_max, wait_min
    for i, raw_data in enumerate(all_followings, start=1):
        following = build_following(raw_data)
        try:
            logger.info(f"{i}/{following_count} {following.start_msg}")
            run_one(following)
        except CookieExpiredError as exc:
            # error_message = (
            #     f"Cookie 已失效，程序退出\n"
            #     f"账号: {following.username} ({following.userid})\n"
            #     f"错误: {exc}"
            # )
            # logger.error(error_message)
            raise SystemExit(1) from exc
        except Exception:
            logger.error(traceback.format_exc())
        finally:
            if not options.use_local_json and wait_max > 0 and i < following_count:
                wait_seconds = random.randint(wait_min, wait_max)
                if wait_seconds > 0:
                    resume_time = datetime.now() + timedelta(seconds=wait_seconds)
                    logger.info(following.end_msg)
                    logger.info(
                        f"等待 {wait_seconds} 秒，直到 {resume_time.strftime('%Y-%m-%d %H:%M:%S')} 开始下一个用户\n")
                    sleep(wait_seconds)
            else:
                logger.info(following.end_msg + "\n")
    logger.info(finished_message)


def build_common_cli_parser():
    """构建各平台共用命令行参数。"""
    parser = argparse.ArgumentParser(description='Scrapy runner options')
    parser.add_argument('-c', '--config', dest='config', default=argparse.SUPPRESS,
                        help=f'读取配置文件，默认 {DEFAULT_CONFIG_PATH.name}')
    parser.add_argument('--ignore-config', action='store_true', default=argparse.SUPPRESS,
                        help='忽略配置文件，仅使用 CLI 和内置默认值')
    parser.add_argument('-v', '--valid', nargs='+', type=int, default=argparse.SUPPRESS, choices=[-2, -1, 0, 1, 2],
                        help='关注类型，可多选：2 特别关注 1 普通关注 0 很久没更新 -1 不喜欢了 -2 账号失效，默认 2')
    parser.add_argument('-id', '--uid', '--user-id', action='append', dest='user_ids', default=argparse.SUPPRESS,
                        help='按 user.userid 精确筛选，可重复传参')
    parser.add_argument('--name', '--username', action='append', dest='usernames', default=argparse.SUPPRESS,
                        help='按 user.username 精确筛选，可重复传参')
    parser.add_argument('-rn', '--rename', dest='username_like', default=argparse.SUPPRESS,
                        help='按 user.username 模糊筛选，支持输入部分用户名')
    parser.add_argument('--lts', '--latest-time-start', dest='latest_time_start', default=argparse.SUPPRESS,
                        help='筛选 latest_time >= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--lte', '--latest-time-end', dest='latest_time_end', default=argparse.SUPPRESS,
                        help='筛选 latest_time <= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--sts', '--scrapy-time-start', dest='scrapy_time_start', default=argparse.SUPPRESS,
                        help='筛选 scrapy_time >= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--ste', '--scrapy-time-end', dest='scrapy_time_end', default=argparse.SUPPRESS,
                        help='筛选 scrapy_time <= 该时间，格式: YYYY-MM-DD HH:MM:SS')
    parser.add_argument('-s', '--sort', dest='sort_option', type=argparse_sort_option, default=argparse.SUPPRESS,
                        help='排序字段[:asc|desc]，默认 scrapy_time:desc')
    parser.add_argument('-slt', '--set-latest-time', dest='set_latest_time', nargs='?', default=argparse.SUPPRESS,
                        const=DEFAULT_LATEST_TIME, type=argparse_latest_time_override,
                        help='覆盖所有用户 latest_time；不传值或传空值时使用 2000-12-12 12:12:12')
    parser.add_argument('-n', '--no-send', action='store_true', dest='no_send', default=argparse.SUPPRESS,
                        help='仅爬取和下载，不发送 Telegram，也不更新用户 latest_time')
    parser.add_argument('--send', action='store_false', dest='no_send', default=argparse.SUPPRESS,
                        help='显式开启发送，可覆盖配置文件中的 no_send=true')
    parser.add_argument('--send-on-download-failure', action='store_true', dest='send_on_download_failure',
                        default=argparse.SUPPRESS,
                        help='下载出现失败时仍继续发送，默认关闭')
    parser.add_argument('--no-send-on-download-failure', action='store_false', dest='send_on_download_failure',
                        default=argparse.SUPPRESS,
                        help='下载失败时不继续发送，可覆盖配置文件中的 send_on_download_failure=true')
    parser.add_argument('-p', '--progress', dest='download_progress',
                        action='store_false', default=argparse.SUPPRESS, help='关闭下载进度条')
    parser.add_argument('--download-progress', dest='download_progress',
                        action='store_true', default=argparse.SUPPRESS, help='显式开启下载进度条')
    parser.add_argument('--no-download-progress', dest='download_progress',
                        action='store_false', default=argparse.SUPPRESS, help='显式关闭下载进度条')
    parser.add_argument('-j', '--json', '--local-json', dest='local_json', action='store_true',
                        default=argparse.SUPPRESS,
                        help='从本地 json 目录读取数据，而不是实时抓取')
    parser.add_argument('--no-local-json', dest='local_json', action='store_false', default=argparse.SUPPRESS,
                        help='显式关闭本地 JSON 模式')
    parser.add_argument('-l', '--list', dest='show', action='store_true', default=argparse.SUPPRESS,
                        help='只展示筛选后的 user 表记录，不执行爬取和发送')
    parser.add_argument('--run', dest='show', action='store_false', default=argparse.SUPPRESS,
                        help='显式执行抓取流程，可覆盖配置文件中的 list=true')
    parser.add_argument('-rl', '--rate-limit', dest='rate_limit', nargs='+', default=argparse.SUPPRESS,
                        help='每个用户处理后的等待秒数：传 1 个值表示固定秒数，传 2 个值表示随机区间')
    return parser


def build_following_filters(args) -> dict[str, Any]:
    """把 CLI 参数整理成统一的数据库筛选参数。"""
    has_user_search = bool(args.user_ids or args.usernames or args.username_like)
    return {
        'valid_list': [] if has_user_search else args.valid,
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


def build_run_options(platform: str, args: argparse.Namespace) -> RunOptions:
    """从 CLI 参数中提取执行链路需要的运行时参数。"""
    if args.rate_limit is None:
        wait_min, wait_max = (30, 80) if platform == 'instagram' else (0, 0)
    else:
        wait_min, wait_max = argparse_rate_limit(args.rate_limit)

    return RunOptions(
        use_local_json=getattr(args, 'local_json', False),
        no_send=getattr(args, 'no_send', False),
        download_progress=getattr(args, 'download_progress', True),
        send_on_download_failure=getattr(args, 'send_on_download_failure', False),
        scrapy_wait_min_seconds=max(0, wait_min),
        scrapy_wait_max_seconds=max(0, wait_max),
    )


def build_run_context(platform: str, args: argparse.Namespace) -> RunContext:
    """构建单次执行所需的运行时上下文。"""
    return RunContext(
        platform=platform,
        options=build_run_options(platform, args),
        stats=RunStats(platform=platform),
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
    effective_filters = build_following_filters(args)
    effective_valid_list = effective_filters['valid_list']
    summary = [
        f"config={args.config}",
        f"valid={effective_valid_list if effective_valid_list else 'ALL'}",
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
    if args.send_on_download_failure:
        summary.append("send_on_download_failure=True")
    if args.rate_limit is not None:
        summary.append(f"rate_limit={args.rate_limit}")
    if not args.download_progress:
        summary.append("download_progress=False")
    if args.show:
        summary.append("show=True")
    return ', '.join(summary)


def run_platform_main(platform: str,
                      logger,
                      build_following: Callable[[Any], Any],
                      run_one: Callable[[Any, set[str], RunContext], None]):
    """运行平台命令行入口的公共壳层。

    当传入 `--show` 时，只展示筛选结果，不进入抓取链路。
    """
    parser = build_common_cli_parser()
    argv = sys.argv[1:]
    if argv and argv[0] == platform:
        argv = argv[1:]
    args = parse_cli_args(parser, argv, entry_name=platform)
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
    context = build_run_context(platform, args)
    context.stats.matched_users = len(all_followings)
    if not all_followings:
        logger.info(f"{platform} 没有符合条件的用户，本次任务结束")
        logger.info(context.stats.format_summary())
        return args, all_followings
    options = context.options
    logger.info(
        f"{platform} 运行模式: "
        f"local_json={options.use_local_json}, "
        f"no_send={options.no_send}, "
        f"download_progress={options.download_progress}, "
        f"send_on_download_failure={options.send_on_download_failure}, "
        f"scrapy_wait={options.scrapy_wait_min_seconds}-{options.scrapy_wait_max_seconds}s"
    )
    sent_post = set(get_sent_post(platform))
    logger.info(f"{platform} 已加载 {len(sent_post)} 条历史已发送记录")
    logger.info(f"{platform} 开始执行抓取流程")
    run_followings(
        all_followings,
        build_following=build_following,
        run_one=lambda following: run_one(following, sent_post, context),
        logger=logger,
        context=context,
    )
    logger.info(context.stats.format_summary())
    return args, all_followings
