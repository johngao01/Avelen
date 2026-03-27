from __future__ import annotations

import json
import os
import time
import requests
from re import sub
from lxml import etree
from pydash import get

from core.settings import (
    BILIBILI_CONFIG,
    BILIBILI_COOKIE_PATH,
    BILIBILI_JSON_ROOT,
    LOGS_DIR,
)
from core.models import BasePlatform, BasePost, CookieExpiredError, FollowUser, MediaItem, get_platform_logger
from core.scrapy_runner import (
    run_platform_main,
)
from core.utils import (
    build_browser_headers,
    build_platform_json_path,
    load_netscape_cookies,
)
from datetime import datetime

DYNAMIC_API_URL = f"{BILIBILI_CONFIG['api_url']}/x/polymer/web-dynamic/v1/feed/space"
BILIBILI_HEADERS = build_browser_headers(referer=BILIBILI_CONFIG['base_url'])
bilibili_logger = get_platform_logger('bilibili', LOGS_DIR, file_level='DEBUG')
os.makedirs(BILIBILI_JSON_ROOT, exist_ok=True)


class Following(FollowUser):
    """B站关注对象（复用统一 FollowUser）。"""

    def __init__(self, userid, username, latest_time):
        user = FollowUser.from_db_row(userid, username, latest_time)
        super().__init__(user.userid, user.username, user.latest_time)
        self.url = f"{BILIBILI_CONFIG['space_url']}/{self.userid}/dynamic"
        self.start_msg = f'开始获取 {self.username} 截至 {self.latest_time} 的动态，她的主页是 {self.url}'
        self.end_msg = ''


class BilibiliPost(BasePost):
    """B站动态的统一 Post 表示。"""

    def __init__(self, following: Following, node: dict, api: 'BilibiliScrapy | None' = None):
        super().__init__()
        self.following = following
        self.node = node
        self.dynamic_type = node.get('type', '')
        self.idstr = node.get('id_str', '')
        self.basic = node.get('basic') or {}
        self.modules = node.get('modules') or {}
        self.author = self.modules.get('module_author') or {}
        self.platform = 'bilibili'
        self.userid = str(node.get('user_id') or following.userid)
        self.username = following.username
        self.nickname = self.author.get('name') or following.username
        self.mblogid = ''
        self.text_raw = self._resolve_text(api)

    @property
    def create_time(self) -> datetime:
        pub_ts = int(self.author.get('pub_ts') or 0)
        return datetime.fromtimestamp(pub_ts)

    @property
    def url(self) -> str:
        jump_url = self.basic.get('jump_url')
        if jump_url:
            return jump_url
        if self.dynamic_type == 'DYNAMIC_TYPE_AV':
            return f"{BILIBILI_CONFIG['base_url']}/video/{self.video_id}"
        if self.dynamic_type == 'DYNAMIC_TYPE_DRAW':
            return f"{BILIBILI_CONFIG['base_url']}/opus/{self.idstr}"
        return ''

    @property
    def video_id(self) -> str:
        return get(self.modules, 'module_dynamic.major.archive.bvid') or ''

    @property
    def is_top(self) -> bool:
        return get(self.modules, 'module_tag.text') == '置顶'

    @property
    def is_only_fans(self) -> bool:
        return bool(get(self.node, 'basic.is_only_fans'))

    @property
    def badge_text(self) -> str:
        if self.is_only_fans:
            return '充电专属'
        return get(self.modules, 'module_dynamic.major.archive.badge.text') or ''

    def save_json(self) -> None:
        """将 B站动态原始数据保存为本地 JSON，供本地回放模式复用。"""
        json_path = build_platform_json_path('bilibili', self.following.username, f'Dynamic_{self.idstr}.json')
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        data = {**self.node, 'user_id': self.userid, 'username': self.username}
        with open(json_path, mode='w', encoding='utf8') as json_write:
            json.dump(data, json_write, ensure_ascii=False, indent=4)

    def build_media_items(self) -> list[MediaItem]:
        """把 B站视频/图文节点转换成统一媒体列表。"""
        if self.dynamic_type == 'DYNAMIC_TYPE_AV' and self.video_id:
            return [MediaItem(
                url=self.url,
                media_type='video',
                filename_hint=f'{self.username}/%(id)s_%(title)s.%(ext)s',
                referer=self.url,
                ext='mp4',
                index=1,
            )]

        if self.dynamic_type != 'DYNAMIC_TYPE_DRAW':
            return []

        items = []
        draw_items = get(self.node, 'modules.module_dynamic.major.draw.items') or []
        for index, item in enumerate(draw_items, start=1):
            src = item.get('src')
            if not src:
                continue
            ext = src.split('?')[0].split('.')[-1] or 'jpg'
            filename = f'{self.idstr}_{self._safe_fragment(self.text_raw, limit=30)}_{index}.{ext}'
            items.append(MediaItem(
                url=src,
                media_type='photo',
                filename_hint=os.path.join(self.username, filename),
                referer=self.url,
                ext=ext,
                index=index,
            ))
        return items

    def start(self):
        if self.badge_text == '充电专属':
            return False, self.__str__() + ' 充电专属 跳过处理'
        elif duration_text := get(self.modules, 'module_dynamic.major.archive.duration_text'):
            # 视频时长超过10分钟 跳过
            if str(duration_text).startswith('0'):
                return True, self.__str__()
            else:
                return False, self.__str__() + f' 视频过长 {duration_text} 跳过处理'
        elif self.is_only_fans:
            return False, self.__str__() + ' 粉丝专属 跳过处理'
        elif self.dynamic_type in ('DYNAMIC_TYPE_AV', 'DYNAMIC_TYPE_DRAW'):
            return True, self.__str__()
        else:
            return False, self.__str__() + f"{self.dynamic_type}类型 跳过处理"

    def _resolve_text(self, api: 'BilibiliScrapy | None') -> str:
        if self.dynamic_type == 'DYNAMIC_TYPE_AV':
            return get(self.modules, 'module_dynamic.major.archive.title') or get(self.node, 'describe') or ''
        if self.dynamic_type == 'DYNAMIC_TYPE_DRAW':
            desc = get(self.node, 'describe') or ''
            if desc or api is None:
                return desc
            desc = api.get_opus_desc(self.idstr)
            if desc:
                self.node['describe'] = desc
                self.save_json()
            return desc
        return get(self.node, 'describe') or ''

    @staticmethod
    def _safe_fragment(text: str, limit: int = 30) -> str:
        text = text or ''
        if len(text) > limit:
            text = text[:limit]
        text = sub('[\\\\/:*?"<>|\n]', '', text)
        return text or 'post'


class BilibiliScrapy(BasePlatform):
    """B站平台抓取器。"""

    name = 'bilibili'
    aliases = ('bili',)
    content_name = '动态'

    def __init__(self, following: Following, cookies: dict[str, str]):
        self.scraping = following
        self.session = requests.Session()
        self.session.headers.update(BILIBILI_HEADERS)
        for key, value in cookies.items():
            self.session.cookies.set(key, value, domain='.bilibili.com')
        self.logger = bilibili_logger
        self.post: list[BilibiliPost] = []

    def get_post_from_api(self) -> None:
        """实时请求 B站接口，抓取当前账号的新动态。"""
        offset = ''
        page = 1
        keep = True
        while keep:
            try:
                response = self.session.get(
                    DYNAMIC_API_URL,
                    params={'host_mid': self.scraping.userid, 'offset': offset},
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                bilibili_logger.error(f'{self.scraping.username} 获取动态失败: {exc}')
                raise CookieExpiredError(f'Bilibili 爬取数据失败，返回数据无效。')

            if payload.get('code') != 0:
                bilibili_logger.error(f'{self.scraping.username} 获取动态失败。')
                raise CookieExpiredError(f'Bilibili Cookie 已失效, code不为0。')

            data = payload.get('data') or {}
            items = data.get('items') or []
            if not items:
                break

            offset = data.get('offset') or ''
            for item in items:
                item['user_id'] = self.scraping.userid
                item['username'] = self.scraping.username
                post = BilibiliPost(self.scraping, item)
                post.save_json()
                self.post.append(post)
                if post.create_time <= self.scraping.latest_time and not post.is_top:
                    keep = False

            bilibili_logger.info(
                f'第 {page} 页获取到 {len(items)} 个动态, '
                f'一共获取到 {len(self.post)} 个动态'
            )

            if not data.get('has_more'):
                break

            page += 1
            time.sleep(2)

    def get_post_from_local(self) -> None:
        for root, _, files in os.walk(BILIBILI_JSON_ROOT):
            for filename in files:
                if not (filename.startswith('Dynamic_') and filename.endswith('.json')):
                    continue
                json_path = os.path.join(root, filename)
                try:
                    with open(json_path, encoding='utf-8') as file_obj:
                        data = json.load(file_obj)
                except (OSError, json.JSONDecodeError) as exc:
                    bilibili_logger.warning(f'读取本地 B站 JSON 失败: {json_path} {exc}')
                    continue
                if str(data.get('user_id')) != self.scraping.userid:
                    continue
                self.post.append(BilibiliPost(self.scraping, data))
        bilibili_logger.info(f'{self.scraping.username} 从本地 JSON 获取到 {len(self.post)} 个动态')

    def get_opus_desc(self, opus_id: str) -> str:
        """读取图文动态页面，补齐正文描述。"""
        try:
            response = self.session.get(f"{BILIBILI_CONFIG['base_url']}/opus/{opus_id}", timeout=30)
        except Exception as exc:
            bilibili_logger.warning(f'获取 opus {opus_id} 页面失败: {exc}')
            return ''
        if response.status_code != 200:
            bilibili_logger.warning(f'获取 opus {opus_id} 页面失败: http {response.status_code}')
            return ''
        tree = etree.HTML(response.text)
        desc_list = tree.xpath('//div[@class="opus-module-content opus-paragraph-children"]//span/text()')
        return desc_list[0] if desc_list else ''

    @classmethod
    def run(cls):
        return main()


def main():
    cookies = load_netscape_cookies(BILIBILI_COOKIE_PATH)
    return run_platform_main(
        'bilibili',
        bilibili_logger,
        build_following=lambda raw: Following(*raw),
        run_one=lambda following, sent_post, options: BilibiliScrapy(following, cookies).start(sent_post, options),
    )


if __name__ == '__main__':
    main()
