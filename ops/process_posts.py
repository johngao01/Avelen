from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from pydash import get

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_user_by_userid, has_sent_post
from core.models import RunOptions, get_platform_logger, BasePost
from core.scrapy_runner import handle_dispatch_result, send_post_to_telegram
from core.settings import BILIBILI_CONFIG, BILIBILI_JSON_ROOT, DOUYIN_JSON_ROOT, ERROR_FILE, INSTAGRAM_COOKIE_PATH, \
    INSTAGRAM_JSON_ROOT, LOGS_DIR, WEIBO_JSON_ROOT
from core.utils import build_browser_headers, find_file_by_name, log_error, read_text_file
from platforms.bilibili import BilibiliPost, Following as BilibiliFollowing
from platforms.douyin import ABogus, Aweme, DOUYIN_DETAIL_API_URL, Following as DouyinFollowing, favorite_headers
from platforms.instagram import Following as InstagramFollowing, InstagramPost, INSTAGRAM_HOME_URL
from platforms.weibo import Following as WeiboFollowing, WEIBO_API_BASE_URL, WeiboPost, weibo_header

process_posts_logger = get_platform_logger("process_posts", LOGS_DIR, file_level="DEBUG")

PLATFORM_URL_PATTERNS = {
    "douyin": re.compile(
        r"https?://(?:(?:www\.)?douyin\.com/(?:(?:video|note)/\d+)[^\s<>\])]*|v\.douyin\.com/[A-Za-z0-9]+/?[^\s<>\])]*|(?:www\.)?iesdouyin\.com/share/(?:(?:video|note)/\d+)[^\s<>\])]*)",
        re.I),
    "weibo": re.compile(
        r"https?://(?:www\.)?weibo\.com/\d+/[A-Za-z0-9]+[^\s<>\])]*",
        re.I,
    ),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/(?:(?:p|reel|tv)/[A-Za-z0-9_-]+/?)[^\s<>\])]*", re.I),
    "bilibili": re.compile(
        r"https?://(?:(?:www\.)?bilibili\.com/(?:(?:video/[A-Za-z0-9]+)|(?:opus/\d+)|(?:read/cv\d+))[^\s<>\])]*|t\.bilibili\.com/\d+[^\s<>\])]*)",
        re.I),
}


@dataclass(slots=True, frozen=True)
class UrlTask:
    raw_url: str
    normalized_url: str
    platform: str
    post_id: str
    source: str
    source_line: int | None = None


@dataclass(slots=True)
class ResolveResult:
    platform: str
    normalized_url: str
    post_id: str
    post: BasePost | None
    data_source: str | None = None
    api_error: str | None = None
    local_error: str | None = None
    platform_detail: str | None = None


@dataclass(slots=True)
class ProcessSummary:
    # 输入文件总行数；命令行直接传入的 URL 不计入这里。
    input_lines: int = 0
    # 从原始文本中通过平台正则匹配出的 URL 数量。
    matched_urls: int = 0
    # 去重和有效性校验后，最终收集到的待处理任务数。
    collected_tasks: int = 0
    # 因规范化 URL 重复而被跳过的任务数。
    duplicated: int = 0
    # 无法识别为受支持 post URL 的输入数量。
    invalid: int = 0
    # 真正进入处理流程的任务总数。
    total: int = 0
    # 已成功解析成平台 Post 对象的任务数。
    resolved: int = 0
    # 已成功发送到 Telegram 的任务数。
    succeeded: int = 0
    # 因数据库中已存在发送记录而提前跳过的任务数。
    skipped_sent: int = 0
    # 已解析成功，但在平台规则或发送阶段被跳过的任务数。
    skipped_resolved: int = 0
    # API 和本地 JSON 都未能构造成有效 Post 的数量。
    parse_failed: int = 0
    # 已解析成功，但发送到 Telegram 失败的数量。
    send_failed: int = 0
    # 处理过程中发生未预期异常的数量。
    exception_failed: int = 0
    # 直接通过 API 解析成功的数量。
    api_resolved: int = 0
    # 通过本地 JSON 回退解析成功的数量。
    local_resolved: int = 0
    # API 失败后，依靠本地 JSON 成功回退的数量。
    api_failed_then_local_resolved: int = 0
    # API 失败且最终没有成功回退的数量。
    api_failed_without_fallback: int = 0
    # 已进入本地 JSON 回退，但本地回退也失败的数量。
    local_failed: int = 0
    # 各平台进入处理流程的任务数。
    platform_seen: Counter = field(default_factory=Counter)
    # 各平台解析成功的任务数。
    platform_resolved: Counter = field(default_factory=Counter)
    # 各平台发送成功的任务数。
    platform_succeeded: Counter = field(default_factory=Counter)
    # 各平台处理失败的任务数。
    platform_failed: Counter = field(default_factory=Counter)
    # 成功解析任务的数据来源统计，如 api / local。
    source_seen: Counter = field(default_factory=Counter)


def _format_simple_table(headers: list[str], rows: list[list[Any]]) -> str:
    string_rows = [[str(cell) for cell in row] for row in rows]
    widths = [_display_width(header) for header in headers]
    for row in string_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], _display_width(cell))

    def format_row(row: list[str]) -> str:
        return "| " + " | ".join(_pad_display(cell, widths[index]) for index, cell in enumerate(row)) + " |"

    border = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    return "\n".join([border, format_row(headers), border, *[format_row(row) for row in string_rows], border])


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def _pad_display(text: str, width: int) -> str:
    padding = width - _display_width(text)
    return text + " " * max(padding, 0)


def _bool_text(value: bool) -> str:
    return "OK" if value else "MISMATCH"


def _write_lines_atomic(path: Path, lines: list[str]) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    temp_path.replace(path)


def extract_candidate_urls(text: str) -> list[tuple[str, str]]:
    matched: dict[tuple[int, int], tuple[str, str]] = {}
    for platform, pattern in PLATFORM_URL_PATTERNS.items():
        for match in pattern.finditer(text):
            matched[(match.start(), match.end())] = (platform, match.group(0).rstrip(").,]>\"'"))
    return [matched[key] for key in sorted(matched)]


def resolve_redirect_url(input_url: str) -> str:
    actual_url = input_url
    try:
        response = requests.get(input_url, allow_redirects=False, timeout=10)
        redirect_url = response.headers.get("Location", "")
        if redirect_url:
            actual_url = redirect_url
    except Exception:
        pass
    return actual_url.replace("https://www.iesdouyin.com/share", "https://www.douyin.com")


def get_post_platform_and_idstr(text: str) -> tuple[str, str, str]:
    candidates = extract_candidate_urls(text)
    if not candidates:
        raise ValueError(f"未找到有效的 4 平台 post URL: {text}")
    _, actual_url = candidates[0]
    parsed = urlparse(actual_url)
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)
    if "douyin.com" in host or "iesdouyin.com" in host:
        if len(path_parts) >= 2 and path_parts[0] in {"video", "note"}:
            return "douyin", f"https://www.douyin.com/{path_parts[0]}/{path_parts[1]}", path_parts[1]
        raise ValueError(f"暂不支持的抖音 post URL: {actual_url}")
    if "instagram.com" in host:
        if len(path_parts) >= 2 and path_parts[0] in {"p", "reel", "tv"}:
            return "instagram", f"https://www.instagram.com/{path_parts[0]}/{path_parts[1]}/", path_parts[1]
        raise ValueError(f"暂不支持的 Instagram post URL: {actual_url}")
    if "weibo.com" in host or "weibo.cn" in host:
        if len(path_parts) >= 2 and path_parts[0].isdigit():
            return "weibo", f"https://www.weibo.com/{path_parts[0]}/{path_parts[1]}", path_parts[1]
        raise ValueError(f"暂不支持的微博 post URL: {actual_url}")
    if "bilibili.com" in host:
        if len(path_parts) >= 2 and path_parts[0] == "video":
            return "bilibili", f"https://www.bilibili.com/video/{path_parts[1]}", path_parts[1]
        if len(path_parts) >= 2 and path_parts[0] == "opus":
            return "bilibili", f"https://www.bilibili.com/opus/{path_parts[1]}", path_parts[1]
        if len(path_parts) >= 2 and path_parts[0] == "read":
            return "bilibili", f"https://www.bilibili.com/read/{path_parts[1]}", path_parts[1]
        if host == "t.bilibili.com" and path_parts:
            return "bilibili", f"https://t.bilibili.com/{path_parts[0]}", path_parts[0]
        raise ValueError(f"暂不支持的 Bilibili post URL: {actual_url}")
    raise ValueError(f"暂不支持处理该 URL: {actual_url}")


def resolve_following_and_post(post_data, userid_key, following_cls, post_cls) -> BasePost | None:
    userid = get(post_data, userid_key)
    if userid is None:
        return None
    user = get_user_by_userid(userid)
    follower = following_cls(user[0][0], user[0][1], user[0][2]) if user else following_cls("", "favorite", None)
    return post_cls(follower, post_data)


def _load_json(json_path: str | Path):
    with open(json_path, encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _stringify_error(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


def resolve_douyin_post(normalized_url: str, post_id: str) -> ResolveResult:
    try:
        params = {"device_platform": "webapp", "aid": "6383", "channel": "channel_pc_web", "pc_client_type": 1,
                  "version_code": "190500", "version_name": "19.5.0", "cookie_enabled": "true", "screen_width": 1920,
                  "screen_height": 1080, "browser_language": "zh-CN", "browser_platform": "Win32",
                  "browser_name": "Firefox", "browser_version": "124.0", "browser_online": "true",
                  "engine_name": "Gecko", "engine_version": "122.0.0.0", "os_name": "Windows", "os_version": "10",
                  "cpu_core_num": 12, "device_memory": 8, "platform": "PC", "msToken": "", "aweme_id": post_id}
        api_url = f"{DOUYIN_DETAIL_API_URL}{urlencode(params)}&a_bogus={ABogus().ab_model_2_endpoint(params)}"
        headers = favorite_headers.copy()
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        aweme_detail = data['aweme_detail']
        post = resolve_following_and_post(aweme_detail, "author.sec_uid", DouyinFollowing, Aweme)
        if post is None:
            raise ValueError("抖音 API 返回数据缺少 author.sec_uid")
        return ResolveResult("douyin", normalized_url, post_id, post, data_source="api")
    except Exception as exc:
        api_error = _stringify_error(exc)
        try:
            json_path = find_file_by_name(DOUYIN_JSON_ROOT, f"{post_id}.json")
            if not json_path:
                raise FileNotFoundError(f"未找到本地 JSON: {post_id}.json")
            post = resolve_following_and_post(_load_json(json_path), "author.sec_uid", DouyinFollowing, Aweme)
            if post is None:
                raise ValueError("本地抖音 JSON 缺少 author.sec_uid")
            return ResolveResult("douyin", normalized_url, post_id, post, data_source="local", api_error=api_error)
        except Exception as local_exc:
            return ResolveResult("douyin", normalized_url, post_id, None, api_error=api_error,
                                 local_error=_stringify_error(local_exc))


def resolve_weibo_post(normalized_url: str, post_id: str) -> ResolveResult:
    try:
        response = requests.get(f"{WEIBO_API_BASE_URL}/ajax/statuses/show", params={"id": post_id, "locale": "zh-CN"},
                                headers=weibo_header, timeout=10)
        response.raise_for_status()
        post = resolve_following_and_post(response.json(), "user.idstr", WeiboFollowing, WeiboPost)
        if post is None:
            raise ValueError("微博 API 返回数据缺少 user.idstr")
        return ResolveResult("weibo", normalized_url, post.idstr, post, data_source="api")
    except Exception as exc:
        api_error = _stringify_error(exc)
        json_path = find_file_by_name(WEIBO_JSON_ROOT, f"{post_id}.json")
        if not json_path:
            return ResolveResult("weibo", normalized_url, post_id, None, api_error=api_error,
                                 local_error=f"未找到本地 JSON: {post_id}.json")
        try:
            post = resolve_following_and_post(_load_json(json_path), "user.idstr", WeiboFollowing, WeiboPost)
            if post is None:
                raise ValueError("本地微博 JSON 缺少 user.idstr")
            return ResolveResult("weibo", normalized_url, post.idstr, post, data_source="local", api_error=api_error)
        except Exception as local_exc:
            return ResolveResult("weibo", normalized_url, post_id, None, api_error=api_error,
                                 local_error=_stringify_error(local_exc))


def resolve_instagram_post(normalized_url: str, post_id: str) -> ResolveResult:
    def _extract_instagram_json_object(text: str, start: int) -> str:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        raise ValueError("未找到完整的 Instagram 内嵌 JSON 对象")

    try:
        cookie_header = read_text_file(INSTAGRAM_COOKIE_PATH).strip()
        headers = build_browser_headers(referer=f"{INSTAGRAM_HOME_URL}/", cookie=cookie_header,
                                        accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                                        extra={"Cache-Control": "no-cache", "Pragma": "no-cache",
                                               "Upgrade-Insecure-Requests": "1", "sec-fetch-dest": "document",
                                               "sec-fetch-mode": "navigate", "sec-fetch-site": "none",
                                               "sec-fetch-user": "?1"})
        response = requests.get(normalized_url, headers=headers, timeout=30)
        response.raise_for_status()
        key_index = response.text.find('"xdt_api__v1__media__shortcode__web_info"')
        if key_index < 0:
            raise ValueError("Instagram 页面中未找到 shortcode web info")
        begin = response.text.find("{", key_index)
        if begin < 0:
            raise ValueError("Instagram 页面中未找到内嵌 JSON 起点")
        data = json.loads(_extract_instagram_json_object(response.text, begin))
        items = data.get("items") or []
        if not items:
            raise ValueError("Instagram 页面中未找到 items")
        post = resolve_following_and_post(items[0], "user.username", InstagramFollowing, InstagramPost)
        if post is None:
            raise ValueError("Instagram API 返回数据缺少 user.username")
        return ResolveResult("instagram", normalized_url, post_id, post, data_source="api")
    except Exception as exc:
        api_error = _stringify_error(exc)
        try:
            json_path = find_file_by_name(INSTAGRAM_JSON_ROOT, f"{post_id}.json")
            if not json_path:
                raise FileNotFoundError(f"未找到本地 JSON: {post_id}.json")
            post = resolve_following_and_post(_load_json(json_path), "user.username", InstagramFollowing, InstagramPost)
            if post is None:
                raise ValueError("本地 Instagram JSON 缺少 user.username")
            return ResolveResult("instagram", normalized_url, post_id, post, data_source="local", api_error=api_error)
        except Exception as local_exc:
            return ResolveResult("instagram", normalized_url, post_id, None, api_error=api_error,
                                 local_error=_stringify_error(local_exc))


def _seconds_to_duration_text(seconds: int) -> str:
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _build_bilibili_video_node(view: dict[str, Any], bvid: str) -> dict[str, Any]:
    owner = view.get("owner") or {}
    return {"type": "DYNAMIC_TYPE_AV", "id_str": bvid, "user_id": str(owner.get("mid") or ""),
            "username": owner.get("name") or "", "basic": {"jump_url": f"{BILIBILI_CONFIG['base_url']}/video/{bvid}"},
            "modules": {"module_author": {"name": owner.get("name") or "", "pub_ts": int(view.get("ctime") or 0)},
                        "module_dynamic": {"major": {"archive": {"bvid": bvid, "title": view.get("title") or "",
                                                                 "duration_text": _seconds_to_duration_text(
                                                                     int(view.get("duration") or 0)),
                                                                 "badge": {"text": ""}}}}},
            "describe": view.get("desc") or ""}


def resolve_bilibili_post(normalized_url: str, post_id: str) -> ResolveResult:
    try:
        path_parts = [part for part in urlparse(normalized_url).path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] == "video":
            response = requests.get(f"{BILIBILI_CONFIG['api_url']}/x/web-interface/view/detail",
                                    params={"bvid": post_id}, timeout=15)
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise ValueError(f"Bilibili 视频 API 返回异常: code={payload.get('code')}")
            view = (payload.get("data") or {}).get("View") or {}
            if not view:
                raise ValueError("Bilibili 视频 API 返回数据缺少 View")
            post = resolve_following_and_post(_build_bilibili_video_node(view, post_id), "user_id", BilibiliFollowing,
                                              BilibiliPost)
            if post is None:
                raise ValueError("Bilibili 视频 API 返回数据缺少 user_id")
            return ResolveResult("bilibili", normalized_url, post_id, post, data_source="api", platform_detail="video")
        raise ValueError("当前 Bilibili 单帖 API 仅支持 video 链接，其他类型走本地 JSON 回退")
    except Exception as exc:
        api_error = _stringify_error(exc)
        for filename in (f"Dynamic_{post_id}.json", f"{post_id}.json"):
            json_path = find_file_by_name(BILIBILI_JSON_ROOT, filename)
            if not json_path:
                continue
            try:
                post = resolve_following_and_post(_load_json(json_path), "modules.module_author.mid", BilibiliFollowing,
                                                  BilibiliPost)
                if post is None:
                    raise ValueError("本地 Bilibili JSON 缺少 modules.module_author.mid")
                return ResolveResult("bilibili", normalized_url, post_id, post, data_source="local",
                                     api_error=api_error, platform_detail=filename)
            except Exception as local_exc:
                return ResolveResult("bilibili", normalized_url, post_id, None, api_error=api_error,
                                     local_error=_stringify_error(local_exc))
        return ResolveResult("bilibili", normalized_url, post_id, None, api_error=api_error,
                             local_error=f"未找到本地 JSON: Dynamic_{post_id}.json / {post_id}.json")


def resolve_single_post(url: str) -> ResolveResult:
    platform, normalized_url, post_id = get_post_platform_and_idstr(url)
    resolver_map = {
        "douyin": resolve_douyin_post,
        "weibo": resolve_weibo_post,
        "instagram": resolve_instagram_post,
        "bilibili": resolve_bilibili_post,
    }
    if platform in resolver_map:
        return resolver_map[platform](normalized_url, post_id)
    raise ValueError(f"暂不支持处理的平台: {platform}")


class PostBatchProcessor:
    def __init__(self, options: RunOptions, *, skip_sent: bool = True):
        self.options = options
        self.skip_sent = skip_sent
        self.summary = ProcessSummary()

    def _print_scan_progress(self, current: int, total: int, matched: int, collected: int) -> None:
        end = "\n" if current == total else "\r"
        print(f"扫描文件进度 {current}/{total} | 匹配URL {matched} | 有效任务 {collected}", end=end, flush=True)

    def _print_process_progress(self, index: int, total: int, task: UrlTask) -> None:
        percent = (index / total * 100) if total else 100.0
        print(f"处理进度 {index}/{total} ({percent:.1f}%) | platform={task.platform} | url={task.normalized_url}",
              flush=True)

    def _build_tasks_from_text(self, text: str, *, source: str, seen: set[str], source_line: int | None = None) -> list[UrlTask]:
        candidates = extract_candidate_urls(text)
        if not candidates and source == "cli":
            candidates = [("unknown", text.strip())]
        tasks: list[UrlTask] = []
        for platform_hint, raw_url in candidates:
            if platform_hint != "unknown":
                self.summary.matched_urls += 1
            try:
                platform, normalized_url, post_id = get_post_platform_and_idstr(raw_url)
            except ValueError:
                self.summary.invalid += 1
                process_posts_logger.warning(f"source={source} 无法识别为可处理 post URL: {raw_url}")
                continue
            if normalized_url in seen:
                self.summary.duplicated += 1
                process_posts_logger.info(f"source={source} URL 重复，已跳过: {normalized_url}")
                continue
            seen.add(normalized_url)
            tasks.append(UrlTask(raw_url=raw_url, normalized_url=normalized_url, platform=platform, post_id=post_id,
                                 source=source, source_line=source_line))
        return tasks

    def collect_tasks_from_file(self, input_file: Path, seen: set[str]) -> list[UrlTask]:
        lines = input_file.read_text(encoding="utf-8").splitlines()
        self.summary.input_lines += len(lines)
        tasks: list[UrlTask] = []
        process_posts_logger.info(f"开始扫描文件 path={input_file} total_lines={len(lines)}")
        for line_number, line in enumerate(lines, start=1):
            tasks.extend(self._build_tasks_from_text(line, source=f"file:{input_file}#{line_number}", seen=seen, source_line=line_number))
            if lines and (line_number == len(lines) or line_number % 100 == 0):
                self._print_scan_progress(line_number, len(lines), self.summary.matched_urls, len(tasks))
        if not lines:
            print("扫描文件进度 0/0 | 匹配URL 0 | 有效任务 0", flush=True)
        process_posts_logger.info(
            f"文件扫描结束 path={input_file} matched_urls={self.summary.matched_urls} collected_tasks={len(tasks)} duplicated={self.summary.duplicated} invalid={self.summary.invalid}")
        return tasks

    def collect_tasks(self, direct_url: str | None, input_file: Path | None, seen: set[str] | None = None) -> list[
        UrlTask]:
        current_seen = seen if seen is not None else set()
        tasks: list[UrlTask] = []
        if direct_url:
            tasks.extend(self._build_tasks_from_text(direct_url, source="cli", seen=current_seen))
        if input_file:
            tasks.extend(self.collect_tasks_from_file(input_file, current_seen))
        self.summary.collected_tasks += len(tasks)
        return tasks

    def _record_resolution_stats(self, result: ResolveResult) -> None:
        self.summary.resolved += 1
        self.summary.platform_resolved[result.platform] += 1
        self.summary.source_seen[result.data_source or "unknown"] += 1
        if result.data_source == "api":
            self.summary.api_resolved += 1
        elif result.data_source == "local":
            self.summary.local_resolved += 1
            if result.api_error:
                self.summary.api_failed_then_local_resolved += 1

    def process_ready_post(self, result: ResolveResult, source: str, index_text: str, *, record_error: bool = True) -> bool:
        post = result.post
        logger = get_platform_logger(result.platform, LOGS_DIR)
        should_process, start_message = post.start()
        logger.info(
            f"{index_text}\t{start_message} source={source} data_source={result.data_source} api_error={result.api_error or '-'} local_error={result.local_error or '-'}")
        process_posts_logger.info(
            f"{index_text} platform={result.platform} post_id={post.idstr} source={source} data_source={result.data_source} url={post.url} api_error={result.api_error or '-'} local_error={result.local_error or '-'} platform_detail={result.platform_detail or '-'}")
        if not should_process:
            self.summary.skipped_resolved += 1
            return True
        if post is None:
            self.summary.parse_failed += 1
            return True
        status = handle_dispatch_result(send_post_to_telegram(post, logger, options=self.options), logger, post.url,
                                        options=self.options)
        if status in {"success", "skip"}:
            if status == "success":
                self.summary.succeeded += 1
                self.summary.platform_succeeded[result.platform] += 1
            else:
                self.summary.skipped_resolved += 1
            return True
        self.summary.send_failed += 1
        self.summary.platform_failed[result.platform] += 1
        if record_error:
            log_error(post.url, f"process_posts 发送失败 platform={result.platform}")
        return False

    def process_task(self, task: UrlTask, index_text: str, *, record_error: bool = True) -> bool:
        self.summary.total += 1
        self.summary.platform_seen[task.platform] += 1
        try:
            can_precheck_sent = not (task.platform == "weibo" and task.post_id and not str(task.post_id).isdigit())
            if self.skip_sent and task.post_id and can_precheck_sent and has_sent_post(task.post_id):
                print(task.normalized_url, "完成")
                process_posts_logger.info(
                    f"{index_text} 已跳过，数据库中已有记录 platform={task.platform} url={task.normalized_url} post_id={task.post_id}")
                self.summary.skipped_sent += 1
                return True
            result = resolve_single_post(task.normalized_url)
            if result.post is None:
                self.summary.parse_failed += 1
                if result.api_error:
                    self.summary.api_failed_without_fallback += 1
                if result.local_error:
                    self.summary.local_failed += 1
                self.summary.platform_failed[task.platform] += 1
                if record_error:
                    log_error(task.normalized_url,
                              f"process_posts 解析失败 api={result.api_error or '-'} local={result.local_error or '-'}")
                process_posts_logger.error(
                    f"{index_text} 解析失败 platform={task.platform} url={task.normalized_url} api_error={result.api_error or '-'} local_error={result.local_error or '-'}")
                return False
            if self.skip_sent and result.post.idstr and result.post.idstr != task.post_id and has_sent_post(
                    result.post.idstr):
                print(task.normalized_url, "完成")
                process_posts_logger.info(
                    f"{index_text} 已跳过，数据库中已有记录 platform={task.platform} url={task.normalized_url} original_post_id={task.post_id} resolved_post_id={result.post.idstr}")
                self.summary.skipped_sent += 1
                return True
            self._record_resolution_stats(result)
            return self.process_ready_post(result, task.source, index_text, record_error=record_error)
        except Exception:
            self.summary.exception_failed += 1
            self.summary.platform_failed[task.platform] += 1
            if record_error:
                log_error(task.normalized_url, "process_posts 处理异常")
            process_posts_logger.error(
                f"{index_text} 处理异常 source={task.source} url={task.normalized_url}\n{traceback.format_exc()}")
            return False

    def run(self, tasks: list[UrlTask]) -> ProcessSummary:
        process_posts_logger.info(
            f"开始处理 post total={len(tasks)} no_send={self.options.no_send} send_on_download_failure={self.options.send_on_download_failure} skip_sent={self.skip_sent}")
        for index, task in enumerate(tasks, start=1):
            self._print_process_progress(index, len(tasks), task)
            self.process_task(task, f"{index}/{len(tasks)}")
        return self.summary

    def run_error_file(self, error_file: Path) -> ProcessSummary:
        lines = error_file.read_text(encoding="utf-8").splitlines()
        self.summary.input_lines += len(lines)
        process_posts_logger.info(f"开始处理错误文件 path={error_file} total_lines={len(lines)}")
        for line_number, line in enumerate(list(lines), start=1):
            line_seen: set[str] = set()
            tasks = self._build_tasks_from_text(
                line,
                source=f"file:{error_file}#{line_number}",
                seen=line_seen,
                source_line=line_number,
            )
            self.summary.collected_tasks += len(tasks)
            if not tasks:
                continue
            line_success = True
            for task_index, task in enumerate(tasks, start=1):
                self._print_process_progress(task_index, len(tasks), task)
                if not self.process_task(task, f"{line_number}.{task_index}/{len(tasks)}", record_error=False):
                    line_success = False
            if line_success:
                lines[line_number - 1] = ""
                try:
                    _write_lines_atomic(error_file, [current for current in lines if current.strip()])
                except Exception:
                    process_posts_logger.error(f"更新错误文件失败 path={error_file}\n{traceback.format_exc()}")
                    raise
        return self.summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="统一处理 4 平台单个或批量 post URL，自动识别平台、下载内容并发送到 Telegram")
    parser.add_argument("url", nargs="*", help="直接处理一个或多个 post URL")
    parser.add_argument("-i", "--input", help="从文本文件中提取并处理所有可用 post URL")
    parser.add_argument("-n", "--no-send", action="store_true", help="仅下载，不发送")
    parser.add_argument("--send-on-download-failure", action="store_true", help="下载不完整时也继续发送已下载内容")
    parser.add_argument("--no-skip-sent", action="store_true", help="即使数据库里已有发送记录也继续处理")
    return parser


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.input and not Path(args.input).resolve().exists():
        parser.error(f"--input 文件不存在: {Path(args.input).resolve()}")


def print_summary(summary: ProcessSummary) -> None:
    print("处理结果汇总 / Processing Summary")

    completed_total = summary.succeeded + summary.skipped_sent + summary.skipped_resolved
    failed_total = summary.parse_failed + summary.send_failed + summary.exception_failed
    resolved_outcome_total = summary.succeeded + summary.skipped_resolved + summary.send_failed
    unresolved_total = summary.parse_failed + summary.exception_failed
    fallback_total = summary.api_failed_then_local_resolved + summary.api_failed_without_fallback
    invalid_input_total = summary.collected_tasks + summary.invalid + summary.duplicated
    resolution_source_total = summary.api_resolved + summary.local_resolved

    print("\n输入统计 / Input Stats")
    print(_format_simple_table(
        ["字段 / Field", "值 / Value", "关系 / Formula"],
        [
            ["输入行数 / input_lines", summary.input_lines, "-"],
            ["匹配 URL 数 / matched_urls", summary.matched_urls, "-"],
            ["收集任务数 / collected_tasks", summary.collected_tasks, "有效任务"],
            ["重复跳过数 / duplicated", summary.duplicated, "重复 URL"],
            ["无效输入数 / invalid", summary.invalid, "无法识别"],
            ["输入闭环 / input_balance", invalid_input_total, f"collected_tasks + duplicated + invalid = {summary.collected_tasks} + {summary.duplicated} + {summary.invalid}"],
        ],
    ))

    print("\n处理闭环 / Processing Balance")
    print(_format_simple_table(
        ["字段 / Field", "值 / Value", "关系 / Formula"],
        [
            ["处理总数 / total", summary.total, "进入处理流程"],
            ["成功完成 / completed_total", completed_total, f"succeeded + skipped_sent + skipped_resolved = {summary.succeeded} + {summary.skipped_sent} + {summary.skipped_resolved}"],
            ["失败总数 / failed_total", failed_total, f"parse_failed + send_failed + exception_failed = {summary.parse_failed} + {summary.send_failed} + {summary.exception_failed}"],
            ["发送成功数 / succeeded", summary.succeeded, "发送成功"],
            ["已发送跳过数 / skipped_sent", summary.skipped_sent, "数据库已存在"],
            ["解析后跳过数 / skipped_resolved", summary.skipped_resolved, "规则跳过或发送层 skip"],
            ["解析失败数 / parse_failed", summary.parse_failed, "未拿到可用 Post"],
            ["发送失败数 / send_failed", summary.send_failed, "已解析但发送失败"],
            ["异常失败数 / exception_failed", summary.exception_failed, "未预期异常"],
        ],
    ))

    print("\n解析统计 / Resolution Stats")
    print(_format_simple_table(
        ["字段 / Field", "值 / Value", "关系 / Formula"],
        [
            ["解析成功数 / resolved", summary.resolved, "成功构造成 Post"],
            ["解析结果闭环 / resolved_outcome_total", resolved_outcome_total, f"succeeded + skipped_resolved + send_failed = {summary.succeeded} + {summary.skipped_resolved} + {summary.send_failed}"],
            ["未解析完成 / unresolved_total", unresolved_total, f"parse_failed + exception_failed = {summary.parse_failed} + {summary.exception_failed}"],
            ["API 解析成功数 / api_resolved", summary.api_resolved, "直接来自 API"],
            ["本地解析成功数 / local_resolved", summary.local_resolved, "本地 JSON 回退成功"],
            ["来源合计 / resolution_source_total", resolution_source_total, f"api_resolved + local_resolved = {summary.api_resolved} + {summary.local_resolved}"],
            ["API失败后本地成功 / api_failed_then_local_resolved", summary.api_failed_then_local_resolved, "API 失败但本地成功"],
            ["API失败且无回退成功 / api_failed_without_fallback", summary.api_failed_without_fallback, "API 失败且最终失败"],
            ["API失败闭环 / fallback_total", fallback_total, f"api_failed_then_local_resolved + api_failed_without_fallback = {summary.api_failed_then_local_resolved} + {summary.api_failed_without_fallback}"],
            ["本地回退失败数 / local_failed", summary.local_failed, "进入本地回退后仍失败"],
        ],
    ))

    if summary.platform_seen:
        print("\n平台统计 / Platform Stats")
        print(_format_simple_table(
            ["平台 / Platform", "处理数 / Seen", "解析成功 / Resolved", "发送成功 / Succeeded", "失败 / Failed"],
            [
                [
                    platform,
                    summary.platform_seen[platform],
                    summary.platform_resolved[platform],
                    summary.platform_succeeded[platform],
                    summary.platform_failed[platform],
                ]
                for platform in sorted(summary.platform_seen)
            ],
        ))
    if summary.source_seen:
        print("\n来源统计 / Source Stats")
        print(_format_simple_table(
            ["来源 / Source", "数量 / Count"],
            [[source_name, summary.source_seen[source_name]] for source_name in sorted(summary.source_seen)],
        ))

    print("\n一致性检查 / Consistency Checks")
    print(_format_simple_table(
        ["检查项 / Check", "结果 / Result", "说明 / Detail"],
        [
            [
                "处理总数守恒 / total balance",
                _bool_text(summary.total == completed_total + failed_total),
                f"total == completed_total + failed_total -> {summary.total} == {completed_total} + {failed_total}",
            ],
            [
                "解析成功守恒 / resolved balance",
                _bool_text(summary.resolved == resolved_outcome_total),
                f"resolved == succeeded + skipped_resolved + send_failed -> {summary.resolved} == {summary.succeeded} + {summary.skipped_resolved} + {summary.send_failed}",
            ],
            [
                "解析总量守恒 / resolution total balance",
                _bool_text(summary.total == summary.resolved + unresolved_total + summary.skipped_sent),
                f"total == resolved + skipped_sent + parse_failed + exception_failed -> {summary.total} == {summary.resolved} + {summary.skipped_sent} + {summary.parse_failed} + {summary.exception_failed}",
            ],
            [
                "解析来源守恒 / source balance",
                _bool_text(summary.resolved == resolution_source_total),
                f"resolved == api_resolved + local_resolved -> {summary.resolved} == {summary.api_resolved} + {summary.local_resolved}",
            ],
            [
                "输入闭环提示 / input note",
                "INFO",
                f"collected_tasks + duplicated + invalid = {summary.collected_tasks} + {summary.duplicated} + {summary.invalid}",
            ],
        ],
    ))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args, parser)
    options = RunOptions(no_send=args.no_send, send_on_download_failure=args.send_on_download_failure)
    processor = PostBatchProcessor(options, skip_sent=not args.no_skip_sent)
    default_error_mode = not args.url and not args.input
    input_file = Path(args.input).resolve() if args.input else (ERROR_FILE.resolve() if default_error_mode else None)
    is_error_file_mode = input_file is not None and input_file.resolve() == ERROR_FILE.resolve()
    tasks: list[UrlTask] = []
    if is_error_file_mode:
        if not input_file.exists():
            input_file.parent.mkdir(parents=True, exist_ok=True)
            input_file.touch()
        summary = processor.run_error_file(input_file)
    else:
        seen: set[str] = set()
        for direct_url in args.url:
            tasks.extend(processor.collect_tasks(direct_url, None, seen))
        if input_file:
            tasks.extend(processor.collect_tasks(None, input_file, seen))
        if not tasks:
            parser.error("没有找到可处理的 post URL")
        summary = processor.run(tasks)
    print_summary(summary)
    process_posts_logger.info("处理结束")
    failed_total = summary.parse_failed + summary.send_failed + summary.exception_failed + summary.invalid
    return 0 if failed_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
