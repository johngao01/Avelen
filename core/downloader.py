from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import glob
import os
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from threading import local
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from yt_dlp import YoutubeDL
from datetime import datetime
from core.post import BasePost, MediaItem
from core.utils import download_save_root_directory, handler_file, convert_bytes_to_human_readable
from rich.console import Console
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    SpinnerColumn
)

# 初始化 Rich 控制台
console = Console()


class DownloadProgress:
    """单个下载任务的进度视图。

    这个类既可以独立持有一个 `Progress` 实例，
    也可以在并发下载时复用外部传入的共享 `Progress`，
    从而让多个文件同时显示在一组进度条中。
    """

    def __init__(self, filename: str = "Download", progress: Progress | None = None):
        self.start_time = None
        self.end_time = None
        self.total_size = 0
        self.final_filename = filename
        self.owns_progress = progress is None

        # 定义 Rich 进度条样式 (现代、简洁、带渐变感)
        self.progress = progress or self._build_progress()
        self.task_id = None
        self.description = self._short_name(filename)

    @staticmethod
    def _build_progress() -> Progress:
        """构造统一风格的 Rich 进度条。"""
        return Progress(
            "   ",
            SpinnerColumn("dots"),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TransferSpeedColumn(),
            "ETA:",
            TimeRemainingColumn(),
            console=console,
            transient=True  # 下载完成后进度条自动消失
        )

    def live(self):
        """返回一个可用于 `with` 的上下文。

        - 独占进度条时，真正启动/关闭 Rich 的 live 渲染。
        - 共享进度条时，避免重复进入同一个 `Progress` 上下文。
        """
        return self.progress if self.owns_progress else nullcontext()

    @staticmethod
    def _short_name(filename: str) -> str:
        pure_name = os.path.basename(filename or "Download") or "Download"
        return (pure_name[:20] + '..') if len(pure_name) > 20 else pure_name

    def start(self, filename: str | None = None, total: int | None = None):
        """初始化任务并在需要时创建对应进度条。"""
        if self.start_time is None:
            self.start_time = time.time()
        if filename:
            self.final_filename = filename
            self.description = self._short_name(filename)
        if total and total > 0:
            self.total_size = total
        if self.task_id is None:
            self.task_id = self.progress.add_task(
                f"[cyan]{self.description}",
                total=total or None,
            )
            return
        if total and self.progress.tasks[self.task_id].total != total:
            self.progress.update(self.task_id, total=total)

    def update(self, completed: int, *, total: int | None = None, filename: str | None = None):
        """更新已下载字节数；如果总大小可知则一并更新。"""
        total = total if total and total > 0 else None
        if total is not None and completed > total:
            total = completed
        if self.task_id is None:
            self.start(filename=filename, total=total)
        elif filename and filename != self.final_filename:
            self.final_filename = filename
        if total is not None:
            self.total_size = total
        else:
            self.total_size = max(self.total_size, completed)
        update_kwargs = {"completed": completed}
        if total is not None:
            update_kwargs["total"] = total
        self.progress.update(self.task_id, **update_kwargs)

    def finish(self, final_filename: str | None = None, total_size: int | None = None):
        """标记任务结束，并尽量补齐最终文件大小。"""
        if self.start_time is None:
            self.start_time = time.time()
        self.end_time = time.time()
        if final_filename:
            self.final_filename = final_filename
        if total_size is not None and total_size > 0:
            self.total_size = total_size
        elif self.final_filename and os.path.exists(self.final_filename):
            self.total_size = os.path.getsize(self.final_filename)
        if self.task_id is not None:
            completed = self.total_size or int(self.progress.tasks[self.task_id].completed)
            update_kwargs = {"completed": completed}
            if self.total_size:
                update_kwargs["total"] = self.total_size
            self.progress.update(self.task_id, **update_kwargs)

    def progress_hook(self, d):
        """yt-dlp 回调函数"""
        if d['status'] == 'downloading':
            total_size = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            self.update(downloaded, total=total_size, filename=d.get('filename'))

        elif d['status'] == 'finished':
            info_dict = d.get('info_dict') or {}
            self.finish(info_dict.get('_filename') or d.get('filename'))

    def print_final_report(self):
        """下载完成后的单行精简输出"""
        if not self.end_time or not self.start_time or not self.final_filename:
            return

        duration = self.end_time - self.start_time
        speed = self.total_size / duration if duration > 0 else 0
        abspath = os.path.abspath(self.final_filename)
        size = self.total_size
        if os.path.exists(abspath):
            size = os.path.getsize(abspath)
            self.total_size = size

        # 核心输出逻辑：一行展示所有信息，不同颜色标记
        console.print(
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | INFO |\t[white][/white][cyan]{abspath}[/cyan] "
            f"[white][/white][green]{convert_bytes_to_human_readable(size)}[/green] "
            f"[white][/white][yellow]{convert_bytes_to_human_readable(speed)}/s[/yellow] "
            f"[white][/white][magenta]{duration:.2f}s[/magenta]"
        )


@dataclass(slots=True)
class DownloadTask:
    """统一的下载输入描述。"""

    url: str
    save_path: str
    headers: dict | None = None
    timeout: int = 30
    media_type: str = ""
    filename_hint: str = ""
    referer: str | None = None
    ext: str | None = None
    index: int = 1


@dataclass(slots=True)
class DownloadResult:
    """统一的下载结果描述，供发送层直接消费。"""

    task: DownloadTask
    ok: bool
    path: str = ""
    status_code: int = 0
    size: int = 0
    exists: bool = False
    skipped: bool = False
    error: str = ""
    response_headers: dict = field(default_factory=dict)
    dispatch_file: dict | None = None
    response: requests.Response | SimpleNamespace | None = None

    def to_dispatch_file(self) -> dict | None:
        if not self.dispatch_file:
            return None
        return dict(self.dispatch_file)


class Downloader:
    """统一下载入口。

    负责：
    - 将 `BasePost` 转换为 `DownloadTask`
    - 在多个任务之间做并发调度
    - 为 Bilibili 视频自动切换到 `yt-dlp`
    - 将下载结果转换成发送层可直接使用的结构
    """

    def __init__(
            self,
            *,
            root_dir: str = download_save_root_directory,
            timeout: int = 30,
            max_retries: int = 3,
            max_workers: int = 4,
            logger=None,
            session: requests.Session | None = None,
    ):
        self.root_dir = root_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_workers = max_workers
        self.logger = logger
        self._session = session
        self._session_local = local()

    @staticmethod
    def _build_session(max_retries: int) -> requests.Session:
        """创建带重试能力的 requests Session。"""
        session = requests.Session()
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def build_task(self, platform: str, item: MediaItem) -> DownloadTask:
        """把平台层的 `MediaItem` 规范化为下载层任务。"""
        filename_hint = item.filename_hint.replace("/", os.sep).replace("\\", os.sep).lstrip(os.sep)
        if item.ext and not os.path.splitext(filename_hint)[1]:
            filename_hint = f"{filename_hint}.{item.ext.lstrip('.')}"
        headers = dict(item.headers or {})
        if item.referer and "referer" not in {key.lower() for key in headers}:
            headers["Referer"] = item.referer
        save_path = os.path.join(self.root_dir, platform, filename_hint)
        return DownloadTask(
            url=item.url,
            save_path=save_path,
            headers=headers or None,
            timeout=self.timeout,
            media_type=item.media_type,
            filename_hint=filename_hint,
            referer=item.referer,
            ext=item.ext,
            index=item.index,
        )

    def download(self, source: BasePost | DownloadTask | list[DownloadTask]) -> DownloadResult | list[DownloadResult]:
        """统一下载入口。

        支持三种输入：
        - `BasePost`：自动展开为多个媒体任务
        - `DownloadTask`：下载单个文件
        - `list[DownloadTask]`：批量下载多个文件
        """
        if isinstance(source, BasePost):
            tasks = [self.build_task(source.platform, item) for item in source.build_media_items()]
            return self._download_tasks(tasks)
        if isinstance(source, DownloadTask):
            return self._download_task(source)
        if isinstance(source, list):
            return self._download_tasks(source)
        raise TypeError("download() 只支持 BasePost、DownloadTask 或 list[DownloadTask]")

    def _get_session(self) -> requests.Session:
        """获取当前线程专属的 Session。

        并发下载时不要在线程间共享同一个 `requests.Session`，
        这样可以减少连接状态交叉带来的不确定性。
        """
        if self._session is not None:
            return self._session
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = self._build_session(max_retries=self.max_retries)
            self._session_local.session = session
        return session

    def _download_tasks(self, tasks: list[DownloadTask]) -> list[DownloadResult]:
        """批量下载任务。

        多文件时使用线程池并发下载，同时共享一组 Rich 进度条；
        返回结果顺序保持与输入任务顺序一致。
        """
        if not tasks:
            return []
        if len(tasks) == 1 or self.max_workers <= 1:
            return [self._download_task(task) for task in tasks]

        results: list[DownloadResult | None] = [None] * len(tasks)
        progress = DownloadProgress._build_progress()
        max_workers = min(self.max_workers, len(tasks))
        with progress:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # future 与原始索引绑定，确保最终结果顺序稳定。
                future_map = {
                    executor.submit(self._download_task, task, progress): index
                    for index, task in enumerate(tasks)
                }
                for future in as_completed(future_map):
                    index = future_map[future]
                    results[index] = future.result()
        return [result for result in results if result is not None]

    def _download_task(self, task: DownloadTask, progress: Progress | None = None) -> DownloadResult:
        """下载单个任务，并根据 URL/媒体类型选择具体实现。"""
        parsed = urlparse(task.url)
        if task.media_type == "video" and parsed.netloc.endswith("bilibili.com") and "/video/" in parsed.path:
            return self._download_with_yt_dlp(task, progress=progress)
        return self._download_http(task, progress=progress)

    @staticmethod
    def _get_content_length(response: requests.Response) -> int | None:
        """从响应头中提取文件总大小。"""
        content_length = response.headers.get("content-length")
        if not content_length:
            return None
        try:
            total = int(content_length)
        except (TypeError, ValueError):
            return None
        return total if total > 0 else None

    def _download_http(self, task: DownloadTask, *, progress: Progress | None = None) -> DownloadResult:
        """使用普通 HTTP 流式下载文件。"""
        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            return self._build_existing_result(task)
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        tmp_path = f"{task.save_path}.part"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        progress_tracker = DownloadProgress(task.save_path, progress=progress)
        try:
            response = self._get_session().get(
                task.url,
                headers=task.headers,
                stream=True,
                timeout=task.timeout,
            )
            status_code = response.status_code
            if status_code != 200:
                return DownloadResult(
                    task=task,
                    ok=False,
                    status_code=status_code,
                    error=f"http {status_code}",
                    response_headers=dict(response.headers),
                    response=response,
                )
            total_size = self._get_content_length(response)
            downloaded = 0
            with open(tmp_path, mode="wb", buffering=8192) as file_obj:
                with progress_tracker.live():
                    progress_tracker.start(task.save_path, total=total_size)
                    # 分块写入，边下载边刷新进度，避免一次性读入内存。
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file_obj.write(chunk)
                            downloaded += len(chunk)
                            progress_tracker.update(downloaded, total=total_size)
            os.replace(tmp_path, task.save_path)
            progress_tracker.finish(task.save_path)
            if progress_tracker.owns_progress:
                progress_tracker.print_final_report()
            result = self._build_result(task, response=response, status_code=status_code)
            return result
        except Exception as exc:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return DownloadResult(task=task, ok=False, error=str(exc))

    def _download_with_yt_dlp(self, task: DownloadTask, *, progress: Progress | None = None) -> DownloadResult:
        """使用 `yt-dlp` 下载 Bilibili 视频并复用统一进度展示。"""
        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            return self._build_existing_result(task)
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        progress_tracker = DownloadProgress(task.save_path, progress=progress)
        try:
            with progress_tracker.live():
                with YoutubeDL({  # type: ignore
                    'logger': self.logger,
                    "cookiefile": str(self._bilibili_cookie_path()),
                    "outtmpl": task.save_path,
                    "format": "bestvideo+bestaudio/best",
                    "merge_output_format": "mp4",
                    "fragment_retries": 10,
                    "retries": 10,
                    "ignoreerrors": False,
                    "writeinfojson": True,
                    "progress_hooks": [progress_tracker.progress_hook],
                    "noprogress": True,
                    "quiet": True,
                }) as ydl:
                    ydl.extract_info(task.url, download=True)
            final_path = task.save_path
            if not os.path.exists(final_path):
                final_path = self._find_downloaded_path(task.save_path)
            if not final_path or not os.path.exists(final_path):
                return DownloadResult(task=task, ok=False, error="yt-dlp output missing")
            progress_tracker.finish(final_path)
            if progress_tracker.owns_progress:
                progress_tracker.print_final_report()
            self._move_bilibili_infojson(final_path)
            return self._build_result(task, response=None, status_code=200, final_path=final_path)
        except Exception as exc:
            return DownloadResult(task=task, ok=False, error=str(exc))

    def _build_existing_result(self, task: DownloadTask) -> DownloadResult:
        """为已存在文件构造“跳过下载”的结果对象。"""
        result = self._build_result(task, response=None, status_code=200)
        result.exists = True
        result.skipped = True
        return result

    def _build_result(
            self,
            task: DownloadTask,
            *,
            response: requests.Response | None,
            status_code: int,
            final_path: str | None = None,
    ) -> DownloadResult:
        """组装统一的下载结果，并预生成发送层所需的文件描述。"""
        path = final_path or task.save_path
        size = os.path.getsize(path) if os.path.exists(path) else 0
        dispatch_file = None
        if size:
            dispatch_file = handler_file(path, task.index, self.logger)
            if dispatch_file:
                dispatch_file = {
                    **dispatch_file,
                    "path": path,
                    "media": path,
                    "caption": dispatch_file.get("caption") or os.path.basename(path),
                    "size": dispatch_file.get("size", size),
                }
        return DownloadResult(
            task=task,
            ok=status_code == 200 and size > 0,
            path=path,
            status_code=status_code,
            size=size,
            response_headers=dict(response.headers) if response is not None else {},
            dispatch_file=dispatch_file,
            response=response,
        )

    @staticmethod
    def _find_downloaded_path(expected_path: str) -> str:
        """在 `yt-dlp` 实际输出扩展名变化时回查真实文件路径。"""
        stem = os.path.splitext(expected_path)[0]
        matched = [
            path for path in glob.glob(f"{stem}.*")
            if not path.endswith((".part", ".info.json"))
        ]
        if matched:
            return matched[0]
        return expected_path

    @staticmethod
    def _bilibili_cookie_path() -> Path:
        """返回 Bilibili cookies 文件路径。"""
        return Path(__file__).resolve().parent.parent / "cookies" / "bl.txt"

    def _move_bilibili_infojson(self, final_path: str):
        """将 `yt-dlp` 生成的 `.info.json` 统一归档到 json 目录。"""
        infojson_path = f"{os.path.splitext(final_path)[0]}.info.json"
        if not os.path.exists(infojson_path):
            return
        save_path = os.path.join(self.root_dir, "bilibili", "json", os.path.basename(infojson_path))
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        os.replace(infojson_path, save_path)
