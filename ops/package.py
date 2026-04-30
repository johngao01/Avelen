from __future__ import annotations

import argparse
import os
import sys
import time
from zipfile import ZipFile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_db_conn
from core.settings import LOGS_DIR
from core.models import get_platform_logger

DEFAULT_FOLDER = "/root/download/"
DEFAULT_PACKAGE_PATH = "/root/download/download.zip"
PACKAGE_LOG_PATH = LOGS_DIR / "package.log"


@dataclass(slots=True)
class PackageStats:
    total: int = 0
    total_bytes: int = 0
    packaged: int = 0
    packaged_bytes: int = 0
    skipped_unsent: int = 0
    skipped_unsent_bytes: int = 0
    deleted: int = 0
    failed: int = 0
    compressed_bytes: int = 0
    failed_files: list[tuple[str, str]] = field(default_factory=list)


def parse_args():
    parser = argparse.ArgumentParser(description="打包已发送文件到 zip，并在成功后删除源文件。")
    parser.add_argument("--folder", default=DEFAULT_FOLDER, help="待打包目录")
    parser.add_argument("--output", default=DEFAULT_PACKAGE_PATH, help="zip 输出路径")
    parser.add_argument(
        "-s",
        "--silent",
        action="store_true",
        help="安静输出：逐文件判定结果不输出到控制台，只写入日志文件。",
    )
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="只统计将要处理的文件，不实际写入 zip，也不删除源文件。默认开启。",
    )
    parser.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        help="实际执行压缩、删除源文件并清理空目录。",
    )
    return parser.parse_args()


def ensure_parent_dir(file_path: str):
    parent_dir = os.path.dirname(file_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)


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
            cursor.execute(
                """
                SELECT COALESCE(CAPTION, ''),
                       COALESCE(IDSTR, ''),
                       COALESCE(MBLOGID, '')
                FROM messages
                """
            )
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


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def process_folder(
        folder: str,
        zip_file: ZipFile | None,
        output_path: str,
        sent_captions: set[str],
        sent_idstrs: set[str],
        sent_mblogids: set[str],
        include_keywords: list[str],
        exclude_keywords: list[str],
        *,
        dry_run: bool,
        logger,
        detail_logger,
):
    stats = PackageStats()
    output_realpath = os.path.realpath(output_path)

    for root, _, files in os.walk(folder):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            real_path = os.path.realpath(file_path)
            if real_path == output_realpath:
                continue

            file_size = os.path.getsize(file_path)
            stats.total += 1
            stats.total_bytes += file_size

            relative_path = os.path.relpath(file_path, folder)
            can_package, reason = is_sent_file(
                relative_path,
                file_name,
                sent_captions,
                sent_idstrs,
                sent_mblogids,
                include_keywords,
                exclude_keywords,
            )
            detail_logger.info(
                f"{stats.total}: {file_path} | 判定结果: {'打包' if can_package else '跳过'} | 命中规则: {reason} | 大小: {format_bytes(file_size)}"
            )
            if not can_package:
                stats.skipped_unsent += 1
                stats.skipped_unsent_bytes += file_size
                continue

            stats.packaged += 1
            stats.packaged_bytes += file_size

            if dry_run:
                continue

            try:
                if zip_file is None:
                    raise RuntimeError("压缩包未打开")
                zip_file.write(file_path, relative_path)
                zip_info = zip_file.getinfo(relative_path)
                stats.compressed_bytes += zip_info.compress_size
                os.remove(file_path)
                stats.deleted += 1
            except FileNotFoundError:
                stats.failed += 1
                stats.failed_files.append((file_path, "文件不存在"))
                logger.warning(f"压缩文件失败: {file_path} - 文件不存在")
            except Exception as exc:
                stats.failed += 1
                stats.failed_files.append((file_path, str(exc)))
                logger.warning(f"压缩文件失败: {file_path} - {exc}")

    return stats


def main():
    logger = get_platform_logger("package", LOGS_DIR)
    args = parse_args()
    folder = args.folder
    package_path = args.output

    if not os.path.isdir(folder):
        logger.error(f"目录不存在: {folder}")
        return 1

    ensure_parent_dir(package_path)

    logger.info(f"待打包目录    : {folder}")
    logger.info(f"输出文件      : {package_path}")
    logger.info(f"包含规则      : {args.include}")
    logger.info(f"排除规则      : {args.exclude}")
    logger.info(f"安静输出      : {args.silent}")
    logger.info(f"仅统计模式    : {args.dry_run}")
    logger.info(f"日志文件      : {PACKAGE_LOG_PATH}")

    detail_logger = logger.bind(file_only=True) if args.silent else logger

    start = time.time()

    try:
        logger.info("从数据库中查询已发送的数据")
        sent_captions, sent_idstrs, sent_mblogids = fetch_sent_file_markers()
        logger.info("从数据库中获取到已发送的数据")
    except Exception as exc:
        logger.exception(f"获取已发送标记失败: {exc}")
        return 1
    stats = PackageStats()
    try:
        if args.dry_run:
            stats = process_folder(
                folder,
                None,
                package_path,
                sent_captions,
                sent_idstrs,
                sent_mblogids,
                args.include,
                args.exclude,
                dry_run=True,
                logger=logger,
                detail_logger=detail_logger,
            )
        else:
            write_mode: Literal["a", "w"] = "a" if os.path.exists(package_path) else "w"
            with ZipFile(package_path, write_mode) as zip_file:
                stats = process_folder(
                    folder,
                    zip_file,
                    package_path,
                    sent_captions,
                    sent_idstrs,
                    sent_mblogids,
                    args.include,
                    args.exclude,
                    dry_run=False,
                    logger=logger,
                    detail_logger=detail_logger,
                )
    except KeyboardInterrupt:
        logger.warning("检测到 Ctrl+C，程序已停止。已经成功保存并删除的文件不会回滚，未处理文件保留在原目录。")
        return 130
    except Exception as exc:
        logger.exception(f"处理文件夹时发生异常: {exc}")
        return 1

    removed_empty_dirs = 0
    if not args.dry_run:
        removed_empty_dirs = cleanup_empty_dirs(folder, logger)

    end = time.time()
    ratio = 0.0 if stats.packaged_bytes == 0 else stats.compressed_bytes / stats.packaged_bytes

    if stats.packaged == 0:
        logger.info("没有匹配到可打包的已发送文件。")

    logger.info(
        f"扫描文件数      : {stats.total}   总大小：{format_bytes(stats.total_bytes)} ({stats.total_bytes} bytes)")
    logger.info(
        f"命中文件数      : {stats.packaged}   总大小：{format_bytes(stats.packaged_bytes)} ({stats.packaged_bytes} bytes)"
    )
    logger.info(
        f"未发送跳过数    : {stats.skipped_unsent}   总大小：{format_bytes(stats.skipped_unsent_bytes)} ({stats.skipped_unsent_bytes} bytes)"
    )
    if stats.deleted:
        logger.info(f"删除文件数      : {stats.deleted}")
    if stats.failed:
        logger.info(f"压缩失败数      : {stats.failed}")
    logger.info(f"压缩后大小      : {format_bytes(stats.compressed_bytes)} ({stats.compressed_bytes} bytes)")
    logger.info(f"压缩率          : {ratio:.2%}")
    logger.info(f"清理空目录数    : {removed_empty_dirs}")
    logger.info(f"耗时            : {end - start:.2f} 秒")

    if stats.failed > 0:
        logger.warning("压缩失败文件列表:")
        for index, (file_path, reason) in enumerate(stats.failed_files, start=1):
            logger.warning(f"{index}. 文件: {file_path}")
            logger.warning(f"   原因: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
