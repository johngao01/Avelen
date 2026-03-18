from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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


class BasePost(ABC):
    """统一内容对象接口。

    平台实现类要把自己的原始作品数据整理成 `BasePost` 子类，
    让下载层和发送层都只依赖统一字段，而不依赖平台私有 JSON 结构。
    """

    def __init__(
        self,
        *,
        platform: str,
        post_id: str,
        user_id: str,
        username: str,
        nickname: str,
        url: str,
        text_raw: str,
        create_time: datetime,
    ):
        self.platform = platform
        self.post_id = str(post_id)
        self.user_id = str(user_id)
        self.username = username
        self.nickname = nickname
        self.url = url
        self.text_raw = text_raw or ""
        self.create_time = create_time
        self._media_items_cache: list[MediaItem] | None = None

    @property
    def media_items(self) -> list[MediaItem]:
        """延迟构建媒体下载列表。

        `build_media_items()` 只会在第一次访问时执行一次，
        后续复用缓存，避免重复解析平台原始数据。
        """
        if self._media_items_cache is None:
            self._media_items_cache = list(self.build_media_items())
        return self._media_items_cache

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
            "username": self.username,
            "nickname": self.nickname,
            "url": self.url,
            "userid": self.user_id,
            "idstr": self.post_id,
            "mblogid": "",
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "text_raw": self.text_raw,
        }


