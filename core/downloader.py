from __future__ import annotations

from dataclasses import dataclass, field
import glob
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from yt_dlp import YoutubeDL

from core.post import BasePost, MediaItem
from core.utils import download_save_root_directory, handler_file


class _SilentLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None


@dataclass(slots=True)
class DownloadTask:
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
    def __init__(
        self,
        *,
        root_dir: str = download_save_root_directory,
        timeout: int = 30,
        max_retries: int = 3,
        logger=None,
        session: requests.Session | None = None,
    ):
        self.root_dir = root_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logger or _SilentLogger()
        self.session = session or self._build_session(max_retries=max_retries)

    @staticmethod
    def _build_session(max_retries: int) -> requests.Session:
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

    def download_post(self, post: BasePost) -> list[DownloadResult]:
        tasks = [self.build_task(post.platform, item) for item in post.media_items]
        return self.download_many(tasks)

    def download_many(self, tasks: list[DownloadTask]) -> list[DownloadResult]:
        return [self.download_one(task) for task in tasks]

    def download_one(self, task: DownloadTask) -> DownloadResult:
        if self._should_use_yt_dlp(task):
            return self._download_with_yt_dlp(task)
        return self._download_http(task)

    def _download_http(self, task: DownloadTask) -> DownloadResult:
        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            return self._build_existing_result(task)
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        tmp_path = f"{task.save_path}.part"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        try:
            response = self.session.get(
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
            with open(tmp_path, mode="wb", buffering=8192) as file_obj:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file_obj.write(chunk)
            os.replace(tmp_path, task.save_path)
            result = self._build_result(task, response=response, status_code=status_code)
            return result
        except Exception as exc:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return DownloadResult(task=task, ok=False, error=str(exc))

    def _download_with_yt_dlp(self, task: DownloadTask) -> DownloadResult:
        if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0:
            return self._build_existing_result(task)
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        try:
            with YoutubeDL({
                "cookiefile": str(self._bilibili_cookie_path()),
                "outtmpl": task.save_path,
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "fragment_retries": 10,
                "retries": 10,
                "ignoreerrors": False,
                "writeinfojson": True,
                "noprogress": True,
                "quiet": True,
            }) as ydl:
                info = ydl.extract_info(task.url, download=True)
            final_path = task.save_path
            if not os.path.exists(final_path):
                final_path = self._find_downloaded_path(task.save_path)
            if not final_path or not os.path.exists(final_path):
                return DownloadResult(task=task, ok=False, error="yt-dlp output missing")
            self._move_bilibili_infojson(final_path)
            return self._build_result(task, response=None, status_code=200, final_path=final_path)
        except Exception as exc:
            return DownloadResult(task=task, ok=False, error=str(exc))

    def _build_existing_result(self, task: DownloadTask) -> DownloadResult:
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
    def _should_use_yt_dlp(task: DownloadTask) -> bool:
        parsed = urlparse(task.url)
        return task.media_type == "video" and parsed.netloc.endswith("bilibili.com") and "/video/" in parsed.path

    @staticmethod
    def _find_downloaded_path(expected_path: str) -> str:
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
        return Path(__file__).resolve().parent.parent / "cookies" / "bl.txt"

    def _move_bilibili_infojson(self, final_path: str):
        infojson_path = f"{os.path.splitext(final_path)[0]}.info.json"
        if not os.path.exists(infojson_path):
            return
        save_path = os.path.join(self.root_dir, "bilibili", "json", os.path.basename(infojson_path))
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        os.replace(infojson_path, save_path)


_legacy_downloader = Downloader()


def download_one(task: DownloadTask):
    result = _legacy_downloader.download_one(task)
    response = result.response or SimpleNamespace(status_code=result.status_code, headers=result.response_headers)
    return result.ok, response


def download_many(tasks: list[DownloadTask]) -> list[DownloadResult]:
    return _legacy_downloader.download_many(tasks)


