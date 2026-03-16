from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class MediaItem:
    url: str
    media_type: str
    filename_hint: str
    headers: dict[str, str] | None = None
    referer: str | None = None
    ext: str | None = None
    index: int = 1


class BasePost(ABC):
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
        if self._media_items_cache is None:
            self._media_items_cache = list(self.build_media_items())
        return self._media_items_cache

    @abstractmethod
    def build_media_items(self) -> list[MediaItem]:
        raise NotImplementedError

    @abstractmethod
    def to_dispatch_data(self, downloaded_files: list[Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    def base_dispatch_data(self) -> dict[str, Any]:
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


