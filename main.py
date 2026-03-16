from __future__ import annotations

import argparse
import runpy
import sys


PLATFORM_MODULES = {
    "weibo": "platforms.weibo",
    "douyin": "platforms.douyin",
    "instagram": "platforms.instagram",
    "bilibili": "platforms.bilibili",
    "bili": "platforms.bilibili",
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Unified scraper entrypoint")
    parser.add_argument("platform", choices=PLATFORM_MODULES.keys(), help="Platform to run")
    return parser.parse_known_args(argv)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        parse_args(argv)
        return
    args, rest = parse_args([argv[0]])
    rest = argv[1:]
    module_name = PLATFORM_MODULES[args.platform]
    sys.argv = [f"{args.platform}.py", *rest]
    runpy.run_module(module_name, run_name="__main__")


if __name__ == "__main__":
    main()


