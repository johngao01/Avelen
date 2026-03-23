from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import requests
import os
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from threading import local
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from yt_dlp import YoutubeDL
from datetime import datetime
from core.models import BasePost, MediaItem
from core.settings import (
    BILIBILI_COOKIE_PATH,
    DOWNLOAD_ROOT,
    MAX_DOCUMENT_SIZE,
    MAX_PHOTO_SIZE,
    MAX_PHOTO_TOTAL_PIXEL,
    MAX_VIDEO_SIZE,
    is_download_progress_enabled,
)
from core.utils import convert_bytes_to_human_readable, get_platform_json_dir
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

    def __init__(self, filename: str = "Download", progress: Progress | None = None, enabled: bool = True):
        self.start_time = None
        self.end_time = None
        self.total_size = 0
        self.final_filename = filename
        self.enabled = enabled
        self.owns_progress = progress is None

        # 定义 Rich 进度条样式 (现代、简洁、带渐变感)
        self.progress = progress if progress is not None else (self.build_progress() if enabled else None)
        self.task_id = None
        self.description = self._short_name(filename)

    @staticmethod
    def build_progress() -> Progress:
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
        if not self.enabled or self.progress is None:
            return nullcontext()
        return self.progress if self.owns_progress else nullcontext()

    @staticmethod
    def _short_name(filename: str) -> str:
        pure_name = os.path.basename(filename or "Download") or "Download"
        return (pure_name[:20] + '..') if len(pure_name) > 20 else pure_name

    def start(self, filename: str | None = None, total: int | None = None):
        """初始化任务并在需要时创建对应进度条。"""
        if not self.enabled or self.progress is None:
            return
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
        if not self.enabled or self.progress is None:
            return
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
        if not self.enabled or self.progress is None:
            return
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
        if not self.enabled:
            return
        if d['status'] == 'downloading':
            total_size = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            self.update(downloaded, total=total_size, filename=d.get('filename'))

        elif d['status'] == 'finished':
            info_dict = d.get('info_dict') or {}
            self.finish(info_dict.get('_filename') or d.get('filename'))

    def print_final_report(self):
        """下载完成后的单行精简输出"""
        if not self.enabled:
            return
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


def format_seconds_to_hms(seconds: float | int | None) -> str:
    if seconds is None:
        return ""
    total_seconds = max(int(round(float(seconds))), 0)
    hour, remainder = divmod(total_seconds, 3600)
    minute, second = divmod(remainder, 60)
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def get_video_duration_hms(path: str) -> str:
    capture = cv2.VideoCapture(path)
    try:
        if not capture.isOpened():
            return ""
        fps = capture.get(cv2.CAP_PROP_FPS)
        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps and fps > 0 and frame_count and frame_count > 0:
            return format_seconds_to_hms(frame_count / fps)
        capture.set(cv2.CAP_PROP_POS_AVI_RATIO, 1)
        duration_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
        if duration_ms and duration_ms > 0:
            return format_seconds_to_hms(duration_ms / 1000)
        return ""
    finally:
        capture.release()


class Downloader:
    """统一下载入口。

    负责：
    - 将 `BasePost` 转换为 `DownloadTask`
    - 下载当前 post 的全部媒体
    - 为 Bilibili 视频自动切换到 `yt-dlp`
    - 下载完成后把 `files` 写入 `post.post_data`
    """

    def __init__(
            self,
            *,
            root_dir: str = DOWNLOAD_ROOT,
            timeout: int = 30,
            max_retries: int = 3,
            max_workers: int = 4,
            show_progress: bool | None = None,
            logger=None,
            session: requests.Session | None = None,
    ):
        self.root_dir = root_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_workers = max_workers
        self.show_progress = is_download_progress_enabled() if show_progress is None else show_progress
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

    def download(self, post: BasePost) -> dict:
        """下载当前 post 的全部媒体，并返回更新后的 `post.post_data`。"""

        def build_file_detail(file_path: str, file_index: int) -> dict | None:
            media_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_ext = media_name.split('.')[-1].lower()
            human_readable_size = convert_bytes_to_human_readable(file_size)
            should_log_file_detail = not self.show_progress and self.logger is not None
            if file_ext in ['jpg', 'png', 'jpeg', 'webp']:
                from PIL import Image
                with Image.open(file_path) as img:
                    resolution = f'{img.width}*{img.height}'
                if should_log_file_detail:
                    msg = ' '.join(["\t", str(file_index), file_path, resolution, human_readable_size])
                    self.logger.info(msg)
                width, height = map(int, resolution.split('*'))
                if width + height > MAX_PHOTO_TOTAL_PIXEL:
                    if file_size < MAX_DOCUMENT_SIZE:
                        return {'filetype': 'document', 'resolution': resolution}
                    return None
                if file_size < MAX_PHOTO_SIZE:
                    return {'filetype': 'photo', 'resolution': resolution}
                if MAX_PHOTO_SIZE < file_size < MAX_DOCUMENT_SIZE:
                    return {'filetype': 'document', 'resolution': resolution}
                return None

            duration = get_video_duration_hms(file_path)
            if duration and should_log_file_detail:
                self.logger.info(' '.join(["\t", str(file_index), file_path, duration, human_readable_size]))
            if file_size < MAX_VIDEO_SIZE:
                return {'filetype': 'video', 'duration': duration}
            return None

        def should_skip_file(file_path: str, file_type: str) -> bool:
            if post.platform != 'weibo' or file_type not in {'photo', 'document'}:
                return False
            is_deleted_media = getattr(post, '_is_deleted_media', None)
            if not callable(is_deleted_media):
                return False
            if is_deleted_media(file_path):
                if self.logger:
                    self.logger.info("和谐的内容：" + file_path)
                return True
            return False

        post_data = post.post_data
        tasks = [self.build_task(post.platform, item) for item in post.build_media_items()]
        if not tasks:
            error = '没有可下载的媒体'
            if self.logger:
                self.logger.error(f'{post.url} {error}')
            post_data['files'] = []
            post_data['ok'] = False
            return post_data

        paths: list[str | None] = [None] * len(tasks)
        progress = DownloadProgress.build_progress() if self.show_progress else None
        if len(tasks) == 1 or self.max_workers <= 1:
            with (progress if progress is not None else nullcontext()):
                for index, task in enumerate(tasks):
                    paths[index] = self._download_media(task, progress)
        else:
            max_workers = min(self.max_workers, len(tasks))
            with (progress if progress is not None else nullcontext()):
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_map = {
                        executor.submit(self._download_media, task, progress): index
                        for index, task in enumerate(tasks)
                    }
                    for future in as_completed(future_map):
                        index = future_map[future]
                        paths[index] = future.result()

        files = []
        failed_urls: list[str] = []
        for task, path in zip(tasks, paths):
            path = path or task.save_path
            size = os.path.getsize(path) if path and os.path.exists(path) else 0
            detail = build_file_detail(path, task.index) if size > 0 else None
            if detail is None or not detail.get('filetype'):
                failed_urls.append(task.url)
                continue
            if should_skip_file(path, detail['filetype']):
                continue
            file_info = {
                'path': path,
                'caption': os.path.basename(path) if path else '',
                'size': size,
                'filetype': detail.get('filetype', ''),
                'detail': detail,
            }
            files.append(file_info)
        post_data['files'] = files
        post_data['ok'] = len(failed_urls) == 0
        if failed_urls and self.logger:
            self.logger.error(f"{post.url} 下载失败：{' | '.join(failed_urls)}")
        return post_data

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

    def _download_media(self, task: DownloadTask, progress: Progress | None = None) -> str:
        """下载单个媒体，并根据 URL/媒体类型选择具体实现。"""
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

    def _download_http(self, task: DownloadTask, *, progress: Progress | None = None) -> str:
        """使用普通 HTTP 流式下载文件。"""
        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            return task.save_path
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        tmp_path = f"{task.save_path}.part"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        progress_tracker = DownloadProgress(task.save_path, progress=progress, enabled=self.show_progress)
        try:
            response = self._get_session().get(
                task.url,
                headers=task.headers,
                stream=True,
                timeout=task.timeout,
            )
            status_code = response.status_code
            if status_code != 200:
                if self.logger:
                    self.logger.error(f"{task.url} 下载失败：http {status_code}")
                return task.save_path
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
            return task.save_path
        except Exception as exc:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if self.logger:
                self.logger.error(f"{task.url} 下载异常：{exc}")
            return task.save_path

    def _download_with_yt_dlp(self, task: DownloadTask, *, progress: Progress | None = None) -> str:
        """使用 `yt-dlp` 下载 Bilibili 视频并复用统一进度展示。"""
        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            return task.save_path
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        progress_tracker = DownloadProgress(task.save_path, progress=progress, enabled=self.show_progress)
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
                    video = ydl.extract_info(task.url, download=True)
                    if not video:
                        if self.logger:
                            self.logger.error(f"{task.url} 下载失败：yt-dlp download error")
                        return task.save_path
            final_path = task.save_path
            if not final_path or not os.path.exists(final_path):
                prepared_path = ydl.prepare_filename(video)
                if prepared_path and os.path.exists(prepared_path):
                    final_path = task.save_path = prepared_path
                if not final_path or not os.path.exists(final_path):
                    if self.logger:
                        self.logger.error(f"{task.url} 下载失败：yt-dlp output missing")
                    return task.save_path
            progress_tracker.finish(final_path)
            if progress_tracker.owns_progress:
                progress_tracker.print_final_report()
            self._move_bilibili_infojson(final_path)
            return final_path
        except Exception as exc:
            if self.logger:
                self.logger.error(f"{task.url} 下载异常：{exc}")
            return task.save_path

    @staticmethod
    def _bilibili_cookie_path() -> Path:
        """返回 Bilibili cookies 文件路径。"""
        return BILIBILI_COOKIE_PATH

    def _move_bilibili_infojson(self, final_path: str):
        """将 `yt-dlp` 生成的 `.info.json` 统一归档到 json 目录。"""
        infojson_path = f"{os.path.splitext(final_path)[0]}.info.json"
        if not os.path.exists(infojson_path):
            return
        username = os.path.basename(os.path.dirname(final_path))
        save_path = os.path.join(get_platform_json_dir('bilibili', username), os.path.basename(infojson_path))
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        os.replace(infojson_path, save_path)
