from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

from loguru import logger as _logger

DEFAULT_LATEST_TIME = datetime(2000, 12, 12, 12, 12, 12)
_STDERR_CONFIGURED = False
_FILE_SINK_KEYS: set[tuple[str, str]] = set()


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


def get_platform_logger(platform_name: str, log_dir: Path, *, file_level: str = 'INFO'):
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
        )
        _STDERR_CONFIGURED = True

    sink_key = (platform_name, str(log_dir.resolve()))
    if sink_key not in _FILE_SINK_KEYS:
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


class BasePlatform(ABC):
    """统一平台抓取器接口。"""

    name: str = ""
    aliases: tuple[str, ...] = ()
    content_name: str = '内容'
    show_time_range: bool = True
    exclude_equal_latest_time: bool = True

    @classmethod
    def all_names(cls) -> tuple[str, ...]:
        """返回平台主名称和别名。"""
        return cls.name, *cls.aliases

    @classmethod
    @abstractmethod
    def run(cls, argv=None):
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

    def filter_new_post(self, sent_urls: set[str]) -> list[Any]:
        """基于抓取结果筛出真正需要处理的内容。"""
        from core.scrapy_runner import filter_new_posts

        return filter_new_posts(
            self.post,
            sent_urls,
            self.scraping.latest_time,
            exclude_equal=self.exclude_equal_latest_time,
            should_sort=self.should_sort_filtered_posts(),
            skip_post=self.should_skip_post_in_filter,
        )

    def start(self, sent_urls: set[str], use_local_json: bool = False) -> None:
        """执行单个 following 的完整处理流程。"""
        from core.scrapy_runner import start_platform_scraping

        start_platform_scraping(
            self,
            sent_urls,
            use_local_json=use_local_json,
            logger=self.logger,
            content_name=self.content_name,
            show_time_range=self.show_time_range,
        )

    def should_skip_post_in_filter(self, post: Any) -> bool:
        """给平台在公共过滤流程里补充自定义跳过规则。"""
        return False

    def should_sort_filtered_posts(self) -> bool:
        """决定过滤后的结果是否按发布时间排序。"""
        return True


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
        return f'{self.username} {self.create_time} {self.url} {self.text_raw}'

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

    @abstractmethod
    def to_dispatch_data(self, downloaded_files: list[Any]) -> dict[str, Any] | None:
        """将下载结果转换成发送层需要的 payload。

        `dispatch_post()` 会先下载媒体，再把下载结果传给这个方法。
        实现类通常会基于 `base_dispatch_data()` 追加 `files` 字段，
        并在下载结果不完整或不满足发送条件时返回 `None`，从而终止发送。
        """
        raise NotImplementedError

    def base_dispatch_data(self) -> dict[str, Any]:
        """构造跨平台共用的发送字段。

        平台实现类可以在 `to_dispatch_data()` 里以此为基础继续补充平台特有字段。
        """
        return {
            'username': self.username,
            'nickname': self.nickname,
            'url': self.url,
            'userid': self.userid,
            'idstr': self.idstr,
            'mblogid': self.mblogid,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            'text_raw': self.text_raw,
        }

    @property
    def create_time_str(self):
        if isinstance(self.create_time, datetime):
            return self.create_time.strftime("%Y-%m-%d %H:%M:%S")
        return '2099-12-12 12:12:12'
