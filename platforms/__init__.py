"""Unified platform registry."""

from __future__ import annotations

from core.models import BasePlatform

from platforms.bilibili import BilibiliScrapy
from platforms.douyin import DouyinScrapy
from platforms.instagram import InstagramScrapy
from platforms.weibo import WeiboScrapy


PLATFORM_CLASSES: tuple[type[BasePlatform], ...] = (
    WeiboScrapy,
    DouyinScrapy,
    InstagramScrapy,
    BilibiliScrapy,
)


def _build_registry() -> dict[str, type[BasePlatform]]:
    registry: dict[str, type[BasePlatform]] = {}
    for platform_cls in PLATFORM_CLASSES:
        for name in platform_cls.all_names():
            key = name.lower()
            if key in registry:
                raise ValueError(f"Duplicate platform name registered: {key}")
            registry[key] = platform_cls
    return registry


PLATFORM_REGISTRY = _build_registry()


def get_platform(name: str) -> type[BasePlatform]:
    return PLATFORM_REGISTRY[name.lower()]


