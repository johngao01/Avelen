from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import requests
import os
import time
from threading import local
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from yt_dlp import YoutubeDL
from datetime import datetime
from core.models import BasePost, DownloadedFile, MediaItem, PostData, DownloadTask
from core.settings import (
    BILIBILI_COOKIE_PATH,
    DOWNLOAD_ROOT,
    MAX_DOCUMENT_SIZE,
    MAX_PHOTO_SIZE,
    MAX_PHOTO_TOTAL_PIXEL,
    MAX_VIDEO_SIZE,
)
from core.utils import convert_bytes_to_human_readable, get_platform_json_dir, bytes2md5
from rich.console import Console
from rich.table import Column
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
del_file = ['7e80fb31ec58b1ca2fb3548480e1b95e', '4cf24fe8401f7ab2eba2c6cb82dffb0e', '41e5d4e3002de5cea3c8feae189f0736',
            '3671086183ed683ec092b43b83fa461c']


class FileDownloadTracker:
    """
    轻量级的单文件下载状态追踪器。
    它不管理界面的生命周期，只负责汇报进度和打印最终的完成日志。
    """

    def __init__(self, task: DownloadTask, progress: Progress, logger=None):
        self.progress = progress
        self.task = task
        self.logger = logger
        self.task_id = None
        self.total_size = 0
        self.start_time = time.time()
        self.end_time = None

    def start(self, total: int | None = None):
        """初始化任务，向主 Progress 注册一个进度条任务"""
        if self.task_id is None:
            self.task_id = self.progress.add_task(f"[cyan]{self.task.rel_path}", total=total or None)

    def update(self, completed: int, total: int | None = None):
        """更新下载进度"""
        if self.task_id is None:
            self.start(total)
        if total:
            self.total_size = total
        self.progress.update(self.task_id, completed=completed, total=self.total_size or None)

    def yt_dlp_hook(self, d):
        """处理 yt-dlp 的回调状态"""
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if self.task_id is None:
                self.task_id = self.progress.add_task(f"[cyan]{self.task.rel_path}", total=total or None)

            self.total_size = total
            self.progress.update(self.task_id, completed=downloaded, total=total or None)

    def finish(self, final_path: str) -> DownloadedFile | None:
        """文件最终落地后调用，获取多媒体信息，打印结果并清理进度条，返回组装好的文件信息。"""
        self.end_time = time.time()

        if not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
            if self.task_id is not None:
                self.progress.remove_task(self.task_id)
            return None

        self.total_size = os.path.getsize(final_path)

        # 微博防和谐机制拦截
        if self.task.platform == 'weibo':
            try:
                with open(final_path, mode='rb') as file_obj:
                    if bytes2md5(file_obj.read()) in del_file:
                        if self.task_id is not None:
                            self.progress.remove_task(self.task_id)
                        return DownloadedFile(
                            path=final_path,
                            size=self.total_size,
                            caption=os.path.basename(final_path),
                            ext=os.path.splitext(final_path)[1][1:].lower(),
                            size_str=convert_bytes_to_human_readable(self.total_size),
                            skipped=True,
                        )
            except OSError:
                pass

        # 获取和解析媒体信息以供日志展示和数据组装
        file_index = str(self.task.index)
        human_readable_size = convert_bytes_to_human_readable(self.total_size)
        media_name = os.path.basename(final_path)
        file_ext = media_name.split('.')[-1].lower()

        file_detail = DownloadedFile(
            path=final_path,
            size=self.total_size,
            caption=media_name,
            size_str=human_readable_size,
            ext=file_ext,
        )

        extra_info = ""

        if file_ext in ['jpg', 'png', 'jpeg', 'webp']:
            try:
                from PIL import Image
                with Image.open(final_path) as img:
                    resolution = f'{img.width}*{img.height}'
                    extra_info = resolution

                width, height = map(int, resolution.split('*'))
                if width + height > MAX_PHOTO_TOTAL_PIXEL:
                    if self.total_size < MAX_DOCUMENT_SIZE:
                        file_detail.filetype = 'document'
                        file_detail.resolution = resolution
                    else:
                        file_detail.skipped = True
                elif self.total_size < MAX_PHOTO_SIZE:
                    file_detail.filetype = 'photo'
                    file_detail.resolution = resolution
                elif MAX_PHOTO_SIZE < self.total_size < MAX_DOCUMENT_SIZE:
                    file_detail.filetype = 'document'
                    file_detail.resolution = resolution
            except Exception:
                extra_info = "无法读取的图片"
                file_detail.filetype = 'photo'
                file_detail.skipped = True
        else:
            duration_str = get_video_duration_hms(final_path)
            extra_info = duration_str
            file_detail.filetype = 'video'
            if self.total_size > MAX_VIDEO_SIZE:
                extra_info = "视频太大"
                file_detail.filetype = 'video'
                file_detail.skipped = True

        # 使用原本 build_file_detail 中的简洁拼接日志样式
        log_msg = ' '.join(["   ", file_index, final_path, extra_info, human_readable_size])

        # 【核心修正】彻底丢弃 logger 输出，强制只使用 progress.console 以保证不撕裂终端 UI
        time_prefix = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.progress.console.print(f"{time_prefix} | INFO | {log_msg}")

        # 任务完成后，立即从动态面板上抹除该任务，避免 100% 进度条长期霸占屏幕
        if self.task_id is not None:
            self.progress.remove_task(self.task_id)
            self.task_id = None

        return file_detail


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
    """统一下载入口。"""

    def __init__(
            self,
            *,
            root_dir: str = DOWNLOAD_ROOT,
            timeout: int = 30,
            max_retries: int = 3,
            max_workers: int = 4,
            show_progress: bool = True,
            logger=None,
            session: requests.Session | None = None,
    ):
        self.root_dir = root_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_workers = max_workers
        self.show_progress = show_progress
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
            platform=platform,
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

    def download(self, post: BasePost) -> PostData:
        """下载当前 post 的全部媒体，并返回更新后的 `post.post_data`。"""
        post_data = post.post_data()
        tasks = [self.build_task(post.platform, item) for item in post.build_media_items()]
        total_file_count = len(tasks)
        skip_file_count = 0

        results: list[DownloadedFile | None] = [None] * len(tasks)

        # 【全局唯一】初始化进度条控制容器
        shared_progress = Progress(
            SpinnerColumn("dots"),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=24),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TransferSpeedColumn(),
            "ETA:",
            TimeRemainingColumn(),
            console=console,
            transient=True,
            expand=True,
            disable=not self.show_progress,
        )

        with shared_progress:
            if len(tasks) == 1 or self.max_workers <= 1:
                for index, task in enumerate(tasks):
                    results[index] = self._download_media(task, shared_progress)
            else:
                max_workers = min(self.max_workers, len(tasks))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_map = {
                        executor.submit(self._download_media, task, shared_progress): index
                        for index, task in enumerate(tasks)
                    }
                    for future in as_completed(future_map):
                        index = future_map[future]
                        results[index] = future.result()

        files: list[DownloadedFile] = []
        for res in results:
            if not res:
                continue
            if res.skipped:
                skip_file_count += 1
                continue
            files.append(res)

        post_data.files = files
        post_data.ok = total_file_count == len(files) + skip_file_count
        return post_data

    def _get_session(self) -> requests.Session:
        """获取当前线程专属的 Session。"""
        if self._session is not None:
            return self._session
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = self._build_session(max_retries=self.max_retries)
            self._session_local.session = session
        return session

    def _download_media(self, task: DownloadTask, shared_progress: Progress) -> DownloadedFile | None:
        """下载单个媒体，并根据 URL/媒体类型选择具体实现。"""
        parsed = urlparse(task.url)
        if task.media_type == "video" and parsed.netloc.endswith("bilibili.com") and "/video/" in parsed.path:
            return self._download_with_yt_dlp(task, shared_progress)
        return self._download_http(task, shared_progress)

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

    def _download_http(self, task: DownloadTask, shared_progress: Progress) -> DownloadedFile | None:
        """使用普通 HTTP 流式下载文件。"""
        tracker = FileDownloadTracker(task, shared_progress, self.logger)

        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            return tracker.finish(task.save_path)

        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        tmp_path = f"{task.save_path}.part"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

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
                return None

            total_size = self._get_content_length(response)
            tracker.start(total_size)
            downloaded = 0

            with open(tmp_path, mode="wb", buffering=8192) as file_obj:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file_obj.write(chunk)
                        downloaded += len(chunk)
                        tracker.update(downloaded, total_size)

            os.replace(tmp_path, task.save_path)
            return tracker.finish(task.save_path)
        except Exception as exc:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            self.logger.error(f"{task.rel_path} 下载异常：{exc}")
            return None

    def _download_with_yt_dlp(self, task: DownloadTask, shared_progress: Progress) -> DownloadedFile | None:
        """使用 `yt-dlp` 下载 Bilibili 视频并复用统一进度展示。"""
        tracker = FileDownloadTracker(task, shared_progress, self.logger)

        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            return tracker.finish(task.save_path)

        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        try:
            with YoutubeDL({  # type: ignore
                'logger': self.logger,
                "cookiefile": str(BILIBILI_COOKIE_PATH),
                "outtmpl": task.save_path,
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "fragment_retries": 10,
                "retries": 10,
                "ignoreerrors": False,
                "writeinfojson": True,
                "progress_hooks": [tracker.yt_dlp_hook],
                "noprogress": True,
                "quiet": True,
            }) as ydl:
                video = ydl.extract_info(task.url, download=True)
                if not video:
                    if self.logger:
                        self.logger.error(f"{task.url} 下载失败：yt-dlp download error")
                    return None

            final_path = task.save_path
            if not final_path or not os.path.exists(final_path):
                prepared_path = ydl.prepare_filename(video)
                if prepared_path and os.path.exists(prepared_path):
                    final_path = task.save_path = prepared_path
                if not final_path or not os.path.exists(final_path):
                    if self.logger:
                        self.logger.error(f"{task.url} 下载失败：yt-dlp output missing")
                    return None

            self._move_bilibili_infojson(final_path)
            return tracker.finish(final_path)
        except Exception as exc:
            if self.logger:
                self.logger.error(f"{task.rel_path} 下载异常：{exc}")
            return None

    def _move_bilibili_infojson(self, final_path: str):
        """将 `yt-dlp` 生成的 `.info.json` 统一归档到 json 目录。"""
        infojson_path = f"{os.path.splitext(final_path)[0]}.info.json"
        if not os.path.exists(infojson_path):
            return
        username = os.path.basename(os.path.dirname(final_path))
        save_path = os.path.join(get_platform_json_dir('bilibili', username), os.path.basename(infojson_path))
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        os.replace(infojson_path, save_path)
