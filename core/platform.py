from __future__ import annotations

from abc import ABC, abstractmethod


class BasePlatform(ABC):
    name: str = ""
    aliases: tuple[str, ...] = ()

    @classmethod
    def all_names(cls) -> tuple[str, ...]:
        return cls.name, *cls.aliases

    @classmethod
    @abstractmethod
    def run(cls, argv=None):
        raise NotImplementedError
