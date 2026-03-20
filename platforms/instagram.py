from __future__ import annotations

import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse

import requests
from core.following import FollowUser
from core.logger import get_platform_logger
from core.platform import BasePlatform
from core.settings import (
    INSTAGRAM_CONFIG,
    INSTAGRAM_COOKIE_PATH,
    INSTAGRAM_JSON_ROOT,
    LOGS_DIR,
)
from core.post import BasePost, MediaItem
from core.scrapy_runner import (
    run_platform_main,
)
from core.utils import (
    build_browser_headers,
    build_platform_json_path,
    get_platform_json_dir,
    read_text_file,
)

GRAPHQL_URL = INSTAGRAM_CONFIG['graphql_url']
PROFILE_DOC_ID = INSTAGRAM_CONFIG['profile_doc_id']
INSTAGRAM_HOME_URL = INSTAGRAM_CONFIG['base_url']

instagram_logger = get_platform_logger('instagram', LOGS_DIR)
os.makedirs(INSTAGRAM_JSON_ROOT, exist_ok=True)


def parse_cookie_header(header: str) -> dict[str, str]:
    pattern = re.compile(r'(?:^|;\s*)([^=;\s]+)=(?:"([^"]*)"|([^;]*))')
    cookies: dict[str, str] = {}
    for match in pattern.finditer(header):
        key = match.group(1)
        value = match.group(2) if match.group(2) is not None else (match.group(3) or '')
        value = re.sub(r'\\([0-7]{3})', lambda current: chr(int(current.group(1), 8)), value)
        value = value.replace('\\"', '"').replace('\\\\', '\\')
        cookies[key] = value
    return cookies


def build_instagram_headers(cookie_header: str) -> dict[str, str]:
    parsed = parse_cookie_header(cookie_header)
    csrftoken = parsed.get('csrftoken', '')
    return build_browser_headers(
        referer=f'{INSTAGRAM_HOME_URL}/',
        cookie=cookie_header,
        accept='*/*',
        extra={
            'Origin': INSTAGRAM_HOME_URL,
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Pragma': 'no-cache',
            'Priority': 'u=1, i',
            'sec-ch-prefers-color-scheme': 'light',
            'sec-ch-ua': '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"',
            'sec-ch-ua-full-version-list': '"Chromium";v="136.0.7103.113", "Microsoft Edge";v="136.0.3240.92", "Not.A/Brand";v="99.0.0.0"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-model': '""',
            'sec-ch-ua-platform': '"Windows"',
            'sec-ch-ua-platform-version': '"19.0.0"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-asbd-id': '359341',
            'x-bloks-version-id': 'f4e32caf235c4c3198ceb3d7599c397741599ea3447ec2f785d4575aeb99766b',
            'x-csrftoken': csrftoken,
            'x-fb-friendly-name': 'PolarisProfilePostsQuery',
            'x-fb-lsd': 'FASx-b1QHr26PyPKzuK9UW',
            'x-ig-app-id': '936619743392459',
            'x-root-field-name': 'xdt_api__v1__feed__user_timeline_graphql_connection',
        },
    )


class Following(FollowUser):
    """Instagram 关注对象（复用统一 FollowUser）。"""

    def __init__(self, pk, username, latest_time):
        user = FollowUser.from_db_row(pk, username, latest_time)
        super().__init__(user.userid, user.username, user.latest_time)
        self.url = f'{INSTAGRAM_HOME_URL}/{self.userid}'
        self.start_msg = (
            f'开始获取 {self.username} 截至 {self.latest_time} 的 Instagram，'
            f'她的主页是 {self.url}'
        )
        self.end_msg = ''


class InstagramPost(BasePost):
    """Instagram 作品的统一 Post 表示。"""

    def __init__(self, following: Following, node: dict):
        super().__init__()
        self.following = following
        self.node = node
        self.shortcode = node.get('shortcode') or node.get('code') or ''
        self.owner = node.get('owner') or {}
        self.owner_username = self.owner.get('username') or following.userid
        self.caption = node.get('caption') or {}
        self.carousel_media = node.get('carousel_media') or []
        self.pin_info = node.get('timeline_pinned_user_ids') or []
        self.platform = 'instagram'
        self.username = following.username
        self.nickname = self.owner_username
        self.userid = following.userid
        self.idstr = self.shortcode
        self.mblogid = str(node.get('id') or '')
        self.create_time = datetime.fromtimestamp(node['taken_at'])
        self.text_raw = self.caption.get('text', '') if self.caption else ''
        self.url = f'{INSTAGRAM_HOME_URL}/p/{self.shortcode}'

    @property
    def is_pinned(self) -> bool:
        if not self.pin_info:
            return False
        owner_pk = str(self.owner.get('pk') or '')
        return owner_pk in {str(item) for item in self.pin_info}

    @property
    def media_count(self) -> int:
        return len(self.build_media_items())

    def start(self):
        if self.is_pinned:
            return False, f'{self} 置顶内容'
        if self.media_count == 0:
            return False, f'{self} 无媒体内容'
        return True, str(self)

    def save_json(self) -> None:
        """将 Instagram 原始数据保存到本地 JSON，供本地回放模式复用。"""
        json_path = build_platform_json_path('instagram', self.following.username, f'{self.shortcode}.json')
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, mode='w', encoding='utf8') as json_write:
            json.dump(self.node, json_write, ensure_ascii=False, indent=4)

    def build_media_items(self) -> list[MediaItem]:
        """将 Instagram 原始媒体节点转换成统一下载任务列表。"""

        # 统一从候选列表里挑分辨率最大的资源，避免把缩略图当成最终文件。
        def pick_largest(medias: list[dict]) -> dict:
            largest: dict = {}
            total_value = 0
            for media in medias:
                size = media.get('height', 0) + media.get('width', 0)
                if size > total_value:
                    total_value = size
                    largest = media
            return largest

        # URL 里拿不到扩展名时，按媒体类型回退默认后缀。
        def detect_extension(url: str, media_type: str) -> str:
            ext = os.path.splitext(urlparse(url).path)[1].lstrip('.')
            if ext:
                return ext
            return 'mp4' if media_type == 'video' else 'jpg'

        headers = build_browser_headers(referer=self.url)
        items: list[MediaItem] = []
        raw_nodes = self.carousel_media or [self.node]

        # Instagram 单条作品可能是单图、单视频，也可能是混合轮播，这里统一展开成下载列表。
        media_entries: list[tuple[str, dict]] = []
        for raw_node in raw_nodes:
            video_versions = raw_node.get('video_versions') or []
            if video_versions:
                video = pick_largest(video_versions)
                if video.get('url'):
                    media_entries.append(('video', video))
                    continue

            image_versions = raw_node.get('image_versions2') or {}
            image_candidates = image_versions.get('candidates') or []
            image = pick_largest(image_candidates)
            if image.get('url'):
                media_entries.append(('photo', image))

        for index, (media_type, media_node) in enumerate(media_entries, start=1):
            url = media_node.get('url') or ''
            if not url:
                continue
            ext = detect_extension(url, media_type)
            filename = f'{self.shortcode}_{index}.{ext}'
            items.append(MediaItem(
                url=url,
                media_type=media_type,
                filename_hint=os.path.join(self.username, filename),
                headers=headers,
                referer=self.url,
                ext=ext,
                index=index,
            ))
        return items

    def to_dispatch_data(self, downloaded_files) -> dict | None:
        """把下载结果转换成发送层需要的 payload。"""
        files = [result.to_dispatch_file() for result in downloaded_files if result.to_dispatch_file()]
        if len(files) != self.media_count:
            instagram_logger.error(self.url + ' 所有内容未全部下载')
            return None
        post_data = self.base_dispatch_data()
        post_data['files'] = files[0] if len(files) == 1 else files
        return post_data


class InstagramScrapy(BasePlatform):
    """Instagram 平台抓取器。"""

    name = 'instagram'
    content_name = '内容'

    def __init__(self, following: Following, cookie_header: str):
        self.scraping = following
        self.session = requests.Session()
        self.session.headers.update(build_instagram_headers(cookie_header))
        self.fb_dtsg = ''
        self.logger = instagram_logger
        self.post: list[InstagramPost] = []

    def ensure_fb_dtsg(self) -> str:
        if self.fb_dtsg:
            return self.fb_dtsg
        response = self.session.get(INSTAGRAM_HOME_URL, timeout=30)
        match = re.search(r'"DTSGInitialData",\[\],\{"token":"([^"]+)"}', response.text)
        if not match:
            raise RuntimeError('fb_dtsg not found')
        self.fb_dtsg = match.group(1)
        instagram_logger.info(f'fb_dtsg value: {self.fb_dtsg}')
        return self.fb_dtsg

    def graphql_request(self, payload_data: dict) -> dict | None:
        try:
            payload = dict(payload_data)
            payload['fb_dtsg'] = self.ensure_fb_dtsg()
            response = self.session.post(GRAPHQL_URL, data=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            instagram_logger.error(f'Instagram GraphQL 请求失败: {exc}')
            return None

    def get_post_from_api(self) -> None:
        """实时请求 Instagram 接口，抓取当前账号的新作品。"""
        self.post = []
        end_cursor = ''
        page = 1
        keep = True
        instagram_logger.info(f'开始获取第 {page} 页数据')
        while keep:
            page_data = self.graphql_request({
                'fb_api_caller_class': 'RelayModern',
                'fb_api_req_friendly_name': 'PolarisProfilePostsQuery',
                'variables': json.dumps(self._build_profile_post_variables(end_cursor)),
                'server_timestamps': 'true',
                'doc_id': PROFILE_DOC_ID,
            })
            if not page_data:
                break
            if not page_data['data']:
                instagram_logger.info(f' {self.scraping.username} 账号可能没了')
                return
            connection = (
                    (page_data.get('data') or {}).get('xdt_api__v1__feed__user_timeline_graphql_connection') or {}
            )
            page_posts = connection.get('edges') or []
            if not page_posts:
                break

            page_info = connection.get('page_info') or {}
            end_cursor = page_info.get('end_cursor') or ''
            keep = bool(page_info.get('has_next_page'))
            page_added = 0

            for edge in page_posts:
                node = edge.get('node') or {}
                if not node:
                    continue
                post = InstagramPost(self.scraping, node)
                if post.is_pinned:
                    continue
                if post.create_time <= self.scraping.latest_time:
                    keep = False
                    break
                post.save_json()
                self.post.append(post)
                page_added += 1

            instagram_logger.info(
                f'{self.scraping.username} 第 {page} 页完成，新增 {page_added} 个内容，累计 {len(self.post)} 个内容'
            )

            if not keep or not end_cursor:
                break
            page += 1
            instagram_logger.info(f'开始获取第 {page} 页数据')

        instagram_logger.info(f'获取 {self.scraping.username} 完成，获取到 {len(self.post)} 个内容')

    def get_post_from_local(self) -> None:
        """从本地 JSON 缓存恢复当前账号的作品列表。"""
        self.post = []
        json_dir = get_platform_json_dir('instagram', self.scraping.username)
        if not os.path.isdir(json_dir):
            instagram_logger.warning(f'{self.scraping.username} 本地 JSON 目录不存在: {json_dir}')
            return

        for filename in os.listdir(json_dir):
            if not filename.endswith('.json'):
                continue
            json_path = os.path.join(json_dir, filename)
            try:
                with open(json_path, encoding='utf-8') as file_obj:
                    node = json.load(file_obj)
            except (OSError, json.JSONDecodeError) as exc:
                instagram_logger.warning(f'读取本地 Instagram JSON 失败: {json_path} {exc}')
                continue

            if 'owner' not in node:
                instagram_logger.warning(f'本地 Instagram JSON 缺少 owner 字段: {json_path}')
                continue
            self.post.append(InstagramPost(self.scraping, node))

        instagram_logger.info(f'{self.scraping.username} 从本地 JSON 获取到 {len(self.post)} 个内容')

    def should_skip_post_in_filter(self, post: InstagramPost) -> bool:
        return post.is_pinned

    def _build_profile_post_variables(self, after: str) -> dict:
        variables = {
            'data': {
                'count': 12,
                'include_reel_media_seen_timestamp': True,
                'include_relationship_info': True,
                'latest_besties_reel_media': True,
                'latest_reel_media': True,
            },
            'username': self.scraping.userid,
            '__relay_internal__pv__PolarisIsLoggedInrelayprovider': True,
            '__relay_internal__pv__PolarisShareSheetV3relayprovider': True,
        }
        if after:
            variables.update({
                'after': after,
                'before': 'null',
                'first': 12,
                'last': 'null',
            })
        return variables

    @classmethod
    def run(cls, argv=None):
        return main(argv)


InstagramPlatform = InstagramScrapy


def main(argv=None):
    cookie_header = read_text_file(INSTAGRAM_COOKIE_PATH)
    return run_platform_main(
        'instagram',
        instagram_logger,
        build_following=lambda raw: Following(*raw),
        run_one=lambda following, sent_urls, args: InstagramScrapy(following, cookie_header).start(
            sent_urls,
            use_local_json=args.local_json,
        ),
        argv=argv,
    )


if __name__ == '__main__':
    main()
