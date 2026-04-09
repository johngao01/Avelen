from __future__ import annotations

import os.path
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import sys
from typing import Any
from core.settings import DOWNLOAD_ROOT

from loguru import logger as _logger
from core.database import update_db

DEFAULT_LATEST_TIME = datetime(2000, 12, 12, 12, 12, 12)
_STDERR_CONFIGURED = False
_FILE_SINK_KEYS: set[tuple[str, str]] = set()


class CookieExpiredError(RuntimeError):
    """Cookie 失效时抛出的异常，用于中断整个程序。"""


@dataclass
class FollowUser:
    """跨平台统一关注用户模型。"""

    userid: str
    username: str
    latest_time: datetime
    url = ''
    start_msg = ''
    end_msg = ''

    @classmethod
    def from_db_row(cls, userid, username, latest_time: str):
        if latest_time is None or latest_time == '':
            parsed = DEFAULT_LATEST_TIME
        elif isinstance(latest_time, datetime):
            parsed = latest_time
        else:
            parsed = datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")
        return cls(userid=userid, username=username, latest_time=parsed)


def get_platform_logger(platform_name: str, log_dir: Path, *, file_level: str = 'DEBUG', file_log: bool = True):
    """返回平台专用 logger，并确保公共 sink 只注册一次。"""
    global _STDERR_CONFIGURED

    log_dir.mkdir(exist_ok=True)
    logger_name = f'scrapy_{platform_name}'

    if not _STDERR_CONFIGURED:
        _logger.remove()
        _logger.add(
            sys.stderr,
            format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
            level='INFO',
            filter=lambda record: not record['extra'].get('file_only', False),
        )
        _STDERR_CONFIGURED = True

    sink_key = (platform_name, str(log_dir.resolve()))
    if file_log and sink_key not in _FILE_SINK_KEYS:
        _logger.add(
            str(log_dir / f'scrapy_{platform_name}.log'),
            format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
            level=file_level,
            encoding='utf-8',
            filter=lambda record, current_name=logger_name: record['extra'].get('name') == current_name,
        )
        _FILE_SINK_KEYS.add(sink_key)

    return _logger.bind(name=logger_name)


@dataclass(slots=True)
class MediaItem:
    """统一的媒体下载描述。

    `Downloader` 不关心平台原始 JSON 长什么样，只消费这个结构。
    平台 Post 实现类需要把自己的媒体节点转换成 `MediaItem` 列表。
    """

    url: str
    media_type: str
    filename_hint: str
    headers: dict[str, str] | None = None
    referer: str | None = None
    ext: str | None = None
    index: int = 1


@dataclass(slots=True)
class DownloadTask:
    """统一的下载输入描述。"""
    platform: str
    url: str
    save_path: str
    headers: dict | None = None
    timeout: int = 30
    media_type: str = ""
    filename_hint: str = ""
    referer: str | None = None
    ext: str | None = None
    index: int = 1

    @property
    def rel_path(self):
        return os.path.relpath(self.save_path, os.path.join(DOWNLOAD_ROOT, self.platform))


@dataclass(slots=True)
class DownloadedFile:
    """下载完成后的标准化文件描述。"""

    path: str
    size: int
    caption: str
    # 文件类型，telegram发送通过这个判断怎么发送
    filetype: str = ""
    # 视频时长
    duration: str = ""
    size_str: str = ""
    ext: str = ""
    # 像素
    resolution: str = ""
    skipped: bool = False


@dataclass(slots=True)
class PostData:
    """跨平台统一发送 payload。"""

    username: str
    nickname: str
    url: str
    userid: str
    idstr: str
    mblogid: str
    create_time: str
    text_raw: str
    files: list[DownloadedFile] = field(default_factory=list)
    ok: bool = False

    @property
    def display_username(self) -> str:
        if self.username == 'favorite' and self.nickname:
            return self.nickname
        return self.username


class BasePlatform(ABC):
    """统一平台抓取器接口。"""

    name: str = ""
    aliases: tuple[str, ...] = ()
    content_name: str = '内容'
    scraping: Any
    post: list[Any]
    logger: Any

    @classmethod
    def all_names(cls) -> tuple[str, ...]:
        """返回平台主名称和别名。"""
        return cls.name, *cls.aliases

    @classmethod
    @abstractmethod
    def run(cls):
        """执行平台命令行入口。"""
        raise NotImplementedError

    @abstractmethod
    def get_post_from_api(self) -> None:
        """从平台远端接口抓取当前账号内容。"""
        raise NotImplementedError

    @abstractmethod
    def get_post_from_local(self) -> None:
        """从本地缓存恢复当前账号内容。"""
        raise NotImplementedError

    def filter_new_post(self, sent_post: set[str]) -> list[Any]:
        """基于统一规则筛出当前平台真正需要处理的新内容。

        过滤顺序：
        - 先按 `sent_post` 去重
        - 再按 `latest_time` 做增量过滤
        - 最后按平台配置决定是否按发布时间排序
        """
        new_posts = []
        for post in self.post:
            if post.idstr in sent_post:
                continue
            if self.scraping.username != 'favorite' and post.create_time < self.scraping.latest_time:
                continue
            new_posts.append(post)
        if self.scraping.username != 'favorite':
            new_posts.sort(key=lambda item: item.create_time)
        return new_posts

    def start(
            self,
            sent_post: set[str],
            options: RunOptions,
    ) -> None:
        """执行单个关注对象的完整处理流程。

        处理顺序：
        - 抓取远端内容，或从本地 JSON 恢复内容
        - 过滤出真正需要处理的新内容
        - 逐条下载并发送到 Telegram
        - 在非 `no-send` 模式下回写数据库进度
        - 生成本次处理的结束摘要日志
        """
        from core.scrapy_runner import handle_dispatch_result, send_post_to_telegram
        from core.utils import (
            build_error_notify_key,
            clear_error_notification,
            send_error_notification,
        )

        if options is None:
            options = RunOptions()

        if options.use_local_json:
            self.get_post_from_local()
        else:
            dedupe_key = build_error_notify_key(
                category='fetch',
                platform=self.name,
                userid=self.scraping.userid,
                username=self.scraping.username,
            )
            try:
                self.get_post_from_api()
            except CookieExpiredError as exc:
                error_message = (
                    f'{self.name} 抓取失败（Cookie 失效）\n'
                    f'账号: {self.scraping.username} ({self.scraping.userid})\n'
                    f'错误: {exc}'
                )
                self.logger.error(error_message)
                send_error_notification(
                    error_message,
                    logger=self.logger,
                    dedupe_key=dedupe_key,
                )
                raise
            except Exception as exc:
                error_message = (
                    f'{self.name} 抓取失败\n'
                    f'账号: {self.scraping.username} ({self.scraping.userid})\n'
                    f'错误: {exc}'
                )
                self.logger.error(error_message)
                send_error_notification(
                    error_message,
                    logger=self.logger,
                    dedupe_key=dedupe_key,
                )
                raise
            else:
                clear_error_notification(dedupe_key, logger=self.logger)

        new_posts = self.filter_new_post(sent_post)
        username = self.scraping.username
        if not new_posts:
            self.scraping.end_msg = f'{username} 处理结束，获取到 {len(self.post)} 个新{self.content_name}，没有新{self.content_name}\n'
        else:
            self.logger.info(
                f'{username} 获取到 {len(self.post)} 个新{self.content_name}，有 {len(new_posts)} 个新{self.content_name}。 '
                f'{new_posts[0].create_time}  {new_posts[-1].create_time}'
            )

        success = 0
        failure = 0
        skipped = 0
        for index, post in enumerate(new_posts, start=1):
            should_process, start_message = post.start()
            self.logger.info(f"{index}/{len(new_posts)} {start_message}")
            if not should_process:
                skipped += 1
                continue
            status = handle_dispatch_result(
                send_post_to_telegram(
                    post,
                    self.logger,
                    options=options,
                ),
                self.logger,
                post.url,
                options=options,
            )
            if status == 'success':
                success += 1
            elif status == 'skip':
                skipped += 1
            else:
                failure += 1
        if self.post:
            latest_post = max(self.post, key=lambda item: item.create_time)
            latest_time = latest_post.create_time_str
        else:
            latest_time = None
        update_db(self.scraping.userid, self.scraping.username, latest_time, options.no_send)
        if new_posts:
            self.scraping.end_msg = (
                f'{username} 处理结束，'
                f'新{self.content_name} {len(new_posts)} 个，'
                f'跳过 {skipped} 个，'
                f'成功 {success} 个，失败 {failure} 个\n'
            )


class BasePost(ABC):
    """统一内容对象接口。

    平台实现类要把自己的原始作品数据整理成 `BasePost` 子类，
    让下载层和发送层都只依赖统一字段，而不依赖平台私有 JSON 结构。
    """

    platform: str
    username: str
    nickname: str
    url: str
    userid: str
    idstr: str
    mblogid: str
    create_time: datetime
    text_raw: str

    def __str__(self) -> str:
        """返回跨平台统一的日志摘要。"""
        return f'{self.username} {self.create_time} {self.url} {self.text_raw.replace("\n", " ")[:50]}'

    @abstractmethod
    def start(self):
        """返回当前 post 是否进入处理流水线，以及对应的日志信息。"""
        raise NotImplementedError

    @abstractmethod
    def build_media_items(self) -> list[MediaItem]:
        """将平台原始媒体结构转换成统一的 `MediaItem` 列表。

        实现类需要在这里完成：
        - 决定每个媒体的下载 URL
        - 决定媒体类型（photo/video/document）
        - 决定文件名、扩展名、请求头和 referer
        - 保证返回顺序与最终发送顺序一致
        """
        raise NotImplementedError

    def post_data(self) -> PostData:
        """构造跨平台共用的发送字段基本信息。

        """
        return PostData(
            username=self.username,
            nickname=self.nickname,
            url=self.url,
            userid=self.userid,
            idstr=self.idstr,
            mblogid=self.mblogid,
            create_time=self.create_time_str,
            text_raw=self.text_raw,
        )

    @property
    def create_time_str(self):
        if isinstance(self.create_time, datetime):
            return self.create_time.strftime("%Y-%m-%d %H:%M:%S")
        return '2099-12-12 12:12:12'

    @property
    @abstractmethod
    def is_top(self):
        raise NotImplementedError


@dataclass(slots=True, frozen=True)
class RunOptions:
    """抓取执行链路共享的运行时参数。"""

    use_local_json: bool = False
    no_send: bool = False
    download_progress: bool = True
    send_on_download_failure: bool = False
    scrapy_wait_min_seconds: int = 0
    scrapy_wait_max_seconds: int = 0
