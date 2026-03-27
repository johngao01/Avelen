from __future__ import annotations

import sys

from core.scrapy_runner import build_common_cli_parser, render_followings_table, select_following_rows
from platforms import PLATFORM_REGISTRY, get_platform


def build_parser():
    """构建统一入口参数。

    `platform` 为可选；省略时根据筛中的 user 记录自动分发到对应平台。
    """
    parser = build_common_cli_parser()
    parser.description = "Unified scraper entrypoint"
    parser.add_argument(
        "platform",
        type=str,
        nargs="?",
        choices=sorted(PLATFORM_REGISTRY.keys()),
        help="Platform to run; omit to auto-detect from matched users",
    )
    return parser


def run_selected_platforms(args):
    """在未显式指定平台时，按 user 表中的平台字段自动分发。"""
    rows = select_following_rows(None, args)
    if args.show:
        render_followings_table(None, rows, show_platform=True)
        return args, rows
    if not rows:
        print("没有符合条件的用户")
        return args, rows

    ordered_platforms = list(dict.fromkeys(row[2] for row in rows))
    for platform_name in ordered_platforms:
        platform_cls = get_platform(platform_name)
        platform_cls.run()
    return args, rows


def main():
    argv = sys.argv[1:]
    parser = build_parser()
    if not argv:
        parser.print_help()
        return None
    args = parser.parse_args(argv)
    if args.platform is None:
        return run_selected_platforms(args)
    platform_cls = get_platform(args.platform)
    return platform_cls.run()


if __name__ == "__main__":
    main()
