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


class DownloadProgress:
    """单个下载任务的进度视图。

    这个类既可以独立持有一个 `Progress` 实例，
    也可以在并发下载时复用外部传入的共享 `Progress`，
    从而让多个文件同时显示在一组进度条中。
    """

    def __init__(self, filename):
        self.start_time = None
        self.end_time = None
        self.total_size = 0
        self.final_filename = filename

        # 定义 Rich 进度条样式 (现代、简洁、带渐变感)
        self.progress = Progress(
            SpinnerColumn("dots"),
            TextColumn(
                "[bold blue]{task.description}",
                table_column=Column(ratio=2, min_width=24)  # 描述列更宽
            ),
            BarColumn(
                bar_width=24,  # 不要用 None
                table_column=Column(ratio=1)  # 进度条列更窄
            ),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TransferSpeedColumn(),
            "ETA:",
            TimeRemainingColumn(),
            console=console,
            transient=True,
            expand=True,
        )
        self.task_id = None
        self.description = os.path.basename(filename)

    def live(self):
        """返回一个可用于 `with` 的上下文。

        - 独占进度条时，真正启动/关闭 Rich 的 live 渲染。
        - 共享进度条时，避免重复进入同一个 `Progress` 上下文。
        """
        return self.progress if is_download_progress_enabled() else nullcontext()

    def start(self, total: int | None = None):
        """初始化任务并在需要时创建对应进度条。"""
        if self.start_time is None:
            self.start_time = time.time()
        self.description = self.final_filename
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
            self.start(total=total)
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

    def finish(self):
        """标记任务结束，并尽量补齐最终文件大小。"""
        if self.start_time is None:
            self.start_time = time.time()
        self.end_time = time.time()
        if self.final_filename and os.path.exists(self.final_filename):
            self.total_size = os.path.getsize(self.final_filename)
        else:
            self.total_size = 0
        if self.task_id is not None:
            completed = self.total_size or int(self.progress.tasks[self.task_id].completed)
            update_kwargs = {"completed": completed}
            if self.total_size:
                update_kwargs["total"] = self.total_size
            self.progress.update(self.task_id, **update_kwargs)

    def progress_hook(self, d):
        """yt-dlp 回调函数"""
        if d['status'] == 'downloading':
            if self.start_time is None:
                self.start_time = time.time()

                # 获取文件大小
            self.total_size = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)

            if self.task_id is None:
                # 提取纯文件名用于进度条显示
                filename = os.path.basename(d.get('filename', 'Video'))
                short_name = (filename[:20] + '..') if len(filename) > 20 else filename
                self.task_id = self.progress.add_task(f"[cyan]{short_name}", total=self.total_size)

            self.progress.update(self.task_id, completed=downloaded)

        elif d['status'] == 'finished':
            self.end_time = time.time()
            # 这里的 filename 可能是临时文件，yt-dlp 会在后续逻辑中更新它
            self.final_filename = d.get('info_dict').get('_filename') or d.get('filename')
            self.finish()

    def print_final_report(self):
        """下载完成后的单行精简输出"""
        duration = self.end_time - self.start_time
        speed = self.total_size / duration if duration > 0 else 0
        self.total_size = os.path.getsize(self.final_filename)

        # 核心输出逻辑：一行展示所有信息，不同颜色标记
        console.print(
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | INFO |\t[white][/white][cyan]{self.final_filename}[/cyan] "
            f"[white][/white][green]{convert_bytes_to_human_readable(self.total_size)}[/green] "
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

    def download(self, post: BasePost) -> dict:
        """下载当前 post 的全部媒体，并返回更新后的 `post.post_data`。"""

        def build_file_detail(file_path: str, file_index: int) -> dict | None:
            media_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_ext = media_name.split('.')[-1].lower()
            human_readable_size = convert_bytes_to_human_readable(file_size)
            file_detail = {'size': file_size, 'caption': media_name, 'duration': 0,
                           'size_str': human_readable_size, 'ext': file_ext}
            should_log_file_detail = not is_download_progress_enabled() and self.logger is not None
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
                        file_detail.update({'filetype': 'document', 'resolution': resolution})
                    else:
                        return None
                elif file_size < MAX_PHOTO_SIZE:
                    file_detail.update({'filetype': 'photo', 'resolution': resolution})
                elif MAX_PHOTO_SIZE < file_size < MAX_DOCUMENT_SIZE:
                    file_detail.update({'filetype': 'document', 'resolution': resolution})
                return file_detail
            duration = get_video_duration_hms(file_path)
            if should_log_file_detail:
                self.logger.info(' '.join(["\t", str(file_index), file_path, duration, human_readable_size]))
            if file_size < MAX_VIDEO_SIZE:
                file_detail.update({'filetype': 'video', 'duration': duration})
                return file_detail
            return None

        def should_skip_file(file_path: str) -> bool:
            """检查下载后的媒体是否命中微博和谐文件特征。"""
            try:
                with open(file_path, mode='rb') as file_obj:
                    return bytes2md5(file_obj.read()) in del_file
            except OSError:
                return False

        post_data = post.post_data()
        tasks = [self.build_task(post.platform, item) for item in post.build_media_items()]
        total_file_count = len(tasks)
        skip_file_count = 0

        paths: list[str | None] = [None] * len(tasks)
        if len(tasks) == 1 or self.max_workers <= 1:
            for index, task in enumerate(tasks):
                paths[index] = self._download_media(task)
        else:
            max_workers = min(self.max_workers, len(tasks))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(self._download_media, task): index
                    for index, task in enumerate(tasks)
                }
                for future in as_completed(future_map):
                    index = future_map[future]
                    paths[index] = future.result()

        files = []
        for task, path in zip(tasks, paths):
            path = path or task.save_path
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                continue
            if post.platform == 'weibo' and should_skip_file(path):
                skip_file_count += 1
                continue
            detail = build_file_detail(path, task.index)
            if not detail:
                continue
            file_info = {
                'path': path,
                **detail
            }
            files.append(file_info)
        post_data['files'] = files
        post_data['ok'] = 1 if total_file_count == len(files) + skip_file_count else 0
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

    def _download_media(self, task: DownloadTask) -> str:
        """下载单个媒体，并根据 URL/媒体类型选择具体实现。"""
        parsed = urlparse(task.url)
        if task.media_type == "video" and parsed.netloc.endswith("bilibili.com") and "/video/" in parsed.path:
            return self._download_with_yt_dlp(task)
        return self._download_http(task)

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

    def _download_http(self, task: DownloadTask) -> str:
        """使用普通 HTTP 流式下载文件。"""
        progress = DownloadProgress(task.save_path)
        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            progress.finish()
            progress.print_final_report()
            return task.save_path
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
                return task.save_path
            total_size = self._get_content_length(response)
            downloaded = 0
            with open(tmp_path, mode="wb", buffering=8192) as file_obj:
                with progress.live():
                    progress.start(total=total_size)
                    # 分块写入，边下载边刷新进度，避免一次性读入内存。
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file_obj.write(chunk)
                            downloaded += len(chunk)
                            progress.update(downloaded, total=total_size)
            os.replace(tmp_path, task.save_path)
            progress.finish()
            progress.print_final_report()
            return task.save_path
        except Exception as exc:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if self.logger:
                self.logger.error(f"{task.url} 下载异常：{exc}")
            return task.save_path

    def _download_with_yt_dlp(self, task: DownloadTask) -> str:
        """使用 `yt-dlp` 下载 Bilibili 视频并复用统一进度展示。"""
        progress = DownloadProgress(task.save_path)
        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            progress.print_final_report()
            return task.save_path
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        try:
            with progress.live():
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
                    "progress_hooks": [progress.progress_hook],
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
            progress.finish(final_path)
            progress.print_final_report()
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
