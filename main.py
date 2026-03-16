from __future__ import annotations

import argparse
import sys

from platforms import PLATFORM_REGISTRY, get_platform


def build_parser():
    parser = argparse.ArgumentParser(description="Unified scraper entrypoint")
    parser.add_argument(
        "platform",
        type=str.lower,
        choices=sorted(PLATFORM_REGISTRY.keys()),
        help="Platform to run",
    )
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        parser.print_help()
        return
    if argv[0] in {"-h", "--help"}:
        parser.print_help()
        return
    args = parser.parse_args([argv[0]])
    platform_cls = get_platform(args.platform)
    return platform_cls.run(argv[1:])


if __name__ == "__main__":
    main()


