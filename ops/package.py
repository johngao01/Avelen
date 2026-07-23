from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_db_conn
from core.settings import LOGS_DIR
from core.models import get_platform_logger

DEFAULT_FOLDER = "/root/download/"
DEFAULT_DEST_FOLDER = "/root/result/"
PACKAGE_LOG_PATH = LOGS_DIR / "package.log"


def parse_args():
    parser = argparse.ArgumentParser(description="打包已发送文件到 zip，并在成功后删除源文件。")
    parser.add_argument("--folder", default=DEFAULT_FOLDER, help="待打包目录")
    parser.add_argument("--output", default=DEFAULT_DEST_FOLDER, help="")
    parser.add_argument(
        "--include",
        nargs="*",
        default=[],
        help="强制打包规则：只要文件路径包含任一字符串，就直接打包，例如 --include json mp4",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="强制跳过规则：只要文件路径包含任一字符串，就直接不打包，例如 --exclude json mp4",
    )
    return parser.parse_args()


def cleanup_empty_dirs(folder: str, logger) -> int:
    logger.info("开始清理空文件夹 --------------->")
    removed = 0
    for root, dirs, _ in os.walk(folder, topdown=False):
        for folder_name in dirs:
            folder_to_check = os.path.join(root, folder_name)
            if not os.listdir(folder_to_check):
                try:
                    os.rmdir(folder_to_check)
                    removed += 1
                    logger.info(f"已删除空文件夹: {folder_to_check}")
                except OSError as exc:
                    logger.warning(f"删除空文件夹失败: {folder_to_check} - {exc}")
    return removed


def fetch_sent_file_markers() -> tuple[set[str], set[str], set[str]]:
    conn = get_db_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(""" SELECT COALESCE(CAPTION, ''), COALESCE(IDSTR, ''), COALESCE(MBLOGID, '')
                               FROM messages""")
            rows = cursor.fetchall()
    finally:
        conn.close()

    captions: set[str] = set()
    idstrs: set[str] = set()
    mblogids: set[str] = set()

    for caption, idstr, mblogid in rows:
        if caption:
            captions.add(str(caption))
        if idstr:
            idstrs.add(str(idstr))
        if mblogid:
            mblogids.add(str(mblogid))
    return captions, idstrs, mblogids


def parse_json_identifiers(file_name: str) -> set[str]:
    stem = Path(file_name).stem
    identifiers = {stem}

    if stem.startswith("Dynamic_"):
        identifiers.add(stem.removeprefix("Dynamic_"))

    if "_" in stem:
        identifiers.update(part for part in stem.split("_") if part)

    return {item for item in identifiers if item}


def is_sent_file(
        relative_path: str,
        file_name: str,
        sent_captions: set[str],
        sent_idstrs: set[str],
        sent_mblogids: set[str],
        include_keywords: list[str],
        exclude_keywords: list[str],
) -> tuple[bool, str]:
    normalized_relative = relative_path.replace("\\", "/")
    normalized_relative_lower = normalized_relative.lower()
    path_parts = normalized_relative.split("/")

    for keyword in exclude_keywords:
        if keyword and keyword.lower() in normalized_relative_lower:
            return False, f"排除规则({keyword})"

    for keyword in include_keywords:
        if keyword and keyword.lower() in normalized_relative_lower:
            return True, f"包含规则({keyword})"

    if "json" in path_parts:
        identifiers = parse_json_identifiers(file_name)
        if identifiers & sent_idstrs:
            return True, "已发送JSON(IDSTR)"
        if identifiers & sent_mblogids:
            return True, "已发送JSON(MBLOGID)"
        return False, "未发送JSON"

    if file_name in sent_captions:
        return True, "已发送媒体(CAPTION)"

    return False, "未发送媒体"


def main():
    logger = get_platform_logger("package", LOGS_DIR)
    args = parse_args()
    folder = str(args.folder)
    dest_folder = str(args.output)

    if not os.path.isdir(folder):
        logger.error(f"目录不存在: {folder}")
        return 0

    logger.info(f"待打包目录    : {folder}")
    logger.info(f"包含规则      : {args.include}")
    logger.info(f"排除规则      : {args.exclude}")
    logger.info(f"日志文件      : {PACKAGE_LOG_PATH}")

    try:
        logger.info("从数据库中查询已发送的数据")
        sent_captions, sent_idstrs, sent_mblogids = fetch_sent_file_markers()
        logger.info("从数据库中获取到已发送的数据")
    except Exception as exc:
        logger.exception(f"获取已发送标记失败: {exc}")
        return 1
    for root, _, files in os.walk(folder):
        for file_name in files:
            file_path = os.path.join(str(root), file_name)
            relative_path = os.path.relpath(file_path, folder)
            can_package, reason = is_sent_file(relative_path, file_name, sent_captions, sent_idstrs, sent_mblogids,
                                               args.include, args.exclude, )
            if not can_package:
                continue
            new_path = os.path.join(dest_folder, relative_path)
            logger.info(f"{file_path}  ----->  {new_path}")
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            shutil.move(file_path, new_path)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
