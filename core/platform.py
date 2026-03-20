from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.scrapy_runner import filter_new_posts, start_platform_scraping


class BasePlatform(ABC):
    """统一平台爬虫接口。

    一个具体平台类负责两件事：
    1. 作为平台注册入口，提供 `run()` 给 CLI/调度层调用。
    2. 作为单个关注账号的抓取器，负责拉取内容并产出该平台的 Post 对象。
    """

    name: str = ""
    aliases: tuple[str, ...] = ()
    content_name: str = '内容'
    show_time_range: bool = True
    exclude_equal_latest_time: bool = True

    @classmethod
    def all_names(cls) -> tuple[str, ...]:
        """返回平台主名称和别名。

        这个结果会被平台注册表和命令行参数复用，因此实现类只需要维护
        `name` / `aliases`，不需要重复处理大小写或注册逻辑。
        """
        return cls.name, *cls.aliases

    @classmethod
    @abstractmethod
    def run(cls, argv=None):
        """执行平台的命令行入口。

        实现类通常会在这里完成：
        - 解析平台参数
        - 读取数据库里的 following 列表
        - 调用 `run_followings()` 驱动整批任务
        """
        raise NotImplementedError

    @abstractmethod
    def get_post_from_api(self) -> None:
        """从平台远端接口抓取当前账号的内容。

        该方法只负责“抓取”本身：
        - 处理分页、签名、请求头等平台细节
        - 把原始响应转换成平台 Post 对象
        - 视需要把原始数据落盘到本地 JSON

        该方法不应该做发送、数据库更新或已发送去重，这些属于后续流水线。
        """
        raise NotImplementedError

    @abstractmethod
    def get_post_from_local(self) -> None:
        """从本地缓存恢复当前账号的内容。

        本地模式的返回结果应与 `get_post_from_api()` 保持一致：
        也就是最终都要产出同一种平台 Post 对象列表，
        这样后面的过滤、下载和发送逻辑才能共用。
        """
        raise NotImplementedError

    def filter_new_post(self, sent_urls: set[str]) -> list[Any]:
        """基于抓取结果筛出真正需要处理的内容。

        这里负责平台自己的业务规则，例如：
        - 跳过超长视频、置顶、直播回放等不支持内容
        - 按 URL/ID 去重，过滤已发送内容
        - 按最终处理顺序排序

        返回值应是可直接交给 `run_posts()` 的 Post 对象列表。
        """
        return filter_new_posts(
            self.post,
            sent_urls,
            self.scraping.latest_time,
            exclude_equal=self.exclude_equal_latest_time,
            should_sort=self.should_sort_filtered_posts(),
            skip_post=self.should_skip_post_in_filter,
        )

    def start(self, sent_urls: set[str], use_local_json: bool = False) -> None:
        """执行单个 following 的完整处理流程。

        该方法负责把一个账号的生命周期串起来：
        - 选择实时抓取或本地恢复
        - 调用过滤逻辑得到真正要处理的 Post
        - 驱动下载、发送和结果处理
        - 在批次结束后更新数据库状态和日志消息

        `start()` 是平台实例级别的主入口；`run()` 则是整个平台批量任务的入口。
        """
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
