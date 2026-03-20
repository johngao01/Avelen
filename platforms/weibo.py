import time
import json
import os
import requests
from typing import Any, Dict

from core.platform import BasePlatform
from core.post import BasePost, MediaItem
from core.following import FollowUser
from datetime import datetime
from core.settings import (
    COMMON_HEADERS,
    LOGS_DIR,
    SCRAPY_FAVORITE_LIMIT,
    WEIBO_CONFIG,
    WEIBO_COOKIE_PATH,
    WEIBO_JSON_ROOT,
)
from core.utils import (
    build_browser_headers,
    build_platform_json_path,
    bytes2md5,
    find_file_by_name,
    get_platform_json_dir,
    log_error,
    read_text_file,
)
from core.scrapy_runner import (
    dispatch_post,
    run_platform_main,
)
from core.logger import get_platform_logger

WEIBO_API_BASE_URL = WEIBO_CONFIG['base_url']
WEIBO_WEB_BASE_URL = WEIBO_CONFIG['web_base_url']
WEIBO_HOME_URL = f'{WEIBO_API_BASE_URL}/'

cookies = read_text_file(WEIBO_COOKIE_PATH)

headers = build_browser_headers(
    referer=WEIBO_HOME_URL,
    cookie=cookies,
    accept=COMMON_HEADERS['json_accept'],
    extra={'X-Requested-With': 'XMLHttpRequest'},
)
# 获取点赞的内容
cookie_headers = build_browser_headers(
    referer=WEIBO_CONFIG['favorite_referer'],
    cookie=cookies,
    accept=COMMON_HEADERS['json_accept'],
    extra={'X-Requested-With': 'XMLHttpRequest'},
)
# 获取单个微博详细信息
weibo_header = build_browser_headers(
    referer=WEIBO_HOME_URL,
    cookie=cookies,
)
del_file = ['7e80fb31ec58b1ca2fb3548480e1b95e', '4cf24fe8401f7ab2eba2c6cb82dffb0e', '41e5d4e3002de5cea3c8feae189f0736',
            '3671086183ed683ec092b43b83fa461c']
VIDEO_URL_KEYS = (
    "mp4_720p_mp4",
    "stream_url",
    "mp4_hd_url",
    "hevc_mp4_hd",
    "mp4_sd_url",
    "mp4_ld_mp4",
    "h265_mp4_hd",
    "h265_mp4_ld",
    "inch_4_mp4_hd",
    "inch_5_5_mp4_hd",
    "inch_5_mp4_hd",
    "stream_url_hd",
)
weibo_logger = get_platform_logger('weibo', LOGS_DIR)


class Following(FollowUser):
    """微博关注对象（复用统一 FollowUser）。"""

    def __init__(self, userid, username, latest_time):
        user = FollowUser.from_db_row(userid, username, latest_time)
        super().__init__(user.userid, user.username, user.latest_time)
        self.url = f'{WEIBO_API_BASE_URL}/u/{self.userid}'
        self.start_msg = f'开始获取 {self.username} 截至 {str(self.latest_time)} 微博，她的主页是 {self.url}'
        self.end_msg = ''


def weibo_edit_count(weibo_info):
    """
    获取微博的修改次数
    :param weibo_info: 微博数据
    :return: 微博的修改次数
    """
    if 'edit_count' in weibo_info:
        edit_count = weibo_info['edit_count']
    elif 'edit_config' in weibo_info:
        edited = weibo_info['edit_config'].get('edited')
        if edited is False:
            edit_count = 0
        else:
            edit_count = weibo_info['edit_count']
    else:
        edit_count = 0
    return edit_count


class WeiboPost(BasePost):
    def __init__(self, following: Following, weibo_data: Dict[str, Any]):
        """基于微博原始数据构造统一 Post 对象。"""
        super().__init__()
        self.following = following
        self.data = weibo_data
        self.platform = 'weibo'
        self.userid = self.data['user']['idstr']
        self.username = following.username
        self.nickname = self.data['user']['screen_name']
        self.idstr = weibo_data.get('idstr', '')
        self.id = self.idstr
        self.url = f'{WEIBO_WEB_BASE_URL}/{self.userid}/{self.idstr}'
        self.text_raw = weibo_data.get('text_raw', '')
        self.mblogid = weibo_data.get('mblogid', '')
        self.create_date = self.create_time.strftime("%Y%m%d")
        self.request_headers = {
            **weibo_header,
            'Referer': f"{WEIBO_WEB_BASE_URL}/{weibo_data['user']['idstr']}/{weibo_data['idstr']}",
        }
        self.is_top = weibo_data.get('isTop', 0)

    def save_json(self):
        """将微博原始数据保存到本地 JSON，供本地回放模式复用。"""
        data = self.data.copy()
        data.pop('weibo_time', None)
        edit_count = weibo_edit_count(self.data)
        suffix = '' if edit_count == 0 else f'_{edit_count}'
        json_path = build_platform_json_path('weibo', self.username, f'{self.idstr}{suffix}.json')
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, mode='w', encoding='utf8') as json_write:
            json.dump(data, json_write, ensure_ascii=False, indent=4)

    def build_media_items(self) -> list[MediaItem]:
        """将微博原始媒体信息转换为统一的下载任务列表。"""
        items: list[MediaItem] = []

        def get_video_url(page_info: dict) -> str | None:
            """从微博视频信息里取出当前可用的视频直链。"""
            media_info = page_info.get('media_info')
            if not media_info:
                return None
            for key in VIDEO_URL_KEYS:
                url = media_info.get(key)
                if url:
                    return url
            return None

        def build_video_item(url: str, idx: int, ext: str = 'mp4') -> MediaItem:
            """构造单个视频媒体项。"""
            return MediaItem(
                url=url,
                media_type='video',
                filename_hint=os.path.join(
                    self.username,
                    f"{self.create_date}_{self.idstr}_{idx}.{ext}",
                ),
                headers=self.request_headers,
                referer=self.url,
                ext=ext,
                index=idx,
            )

        def build_pic_items(picture: dict, idx: int) -> list[MediaItem]:
            """构造单张图片及其 livephoto 视频对应的媒体项。"""
            largest_url = picture['largest']['url']
            file_type = largest_url.split('/')[-1].split('?')[0].split('.')[-1]
            filename = f"{self.create_date}_{self.idstr}_{idx}.{file_type}"
            pic_items = [MediaItem(
                url=largest_url,
                media_type='photo',
                filename_hint=os.path.join(self.username, filename),
                headers=self.request_headers,
                referer=self.url,
                ext=file_type,
                index=idx,
            )]
            if picture.get('type') == 'livephoto' and picture.get('video'):
                pic_items.append(build_video_item(picture['video'], idx, ext='mov'))
            return pic_items

        # 混合图文视频微博：按原始顺序依次展开图片和视频。
        if self.data.get('mix_media_info', {}).get('items'):
            pic_index = 1
            video_index = 1
            for item in self.data['mix_media_info']['items']:
                if item['type'] == 'pic':
                    items.extend(build_pic_items(item['data'], pic_index))
                    pic_index += 1
                elif item['type'] == 'video':
                    video_url = get_video_url(item['data'])
                    if video_url:
                        items.append(build_video_item(video_url, video_index))
                        video_index += 1
            return items

        # 普通图片微博：逐张生成图片任务，livephoto 额外补一个视频任务。
        pic_ids = self.data.get('pic_ids') or []
        pic_infos = self.data.get('pic_infos') or {}
        if pic_ids and pic_infos:
            for index, pic_id in enumerate(pic_ids, start=1):
                pic = pic_infos.get(pic_id)
                if not pic:
                    continue
                items.extend(build_pic_items(pic, index))
            return items

        # 纯视频微博：只生成一个视频任务。
        video_url = get_video_url(self.data.get('page_info') or {})
        if video_url:
            items.append(build_video_item(video_url, 1))
            return items

        return []

    def to_dispatch_data(self, downloaded_files) -> dict | None:
        """将下载结果整理成发送层需要的 webhook 数据。"""
        files = []
        for result in downloaded_files:
            file_data = result.to_dispatch_file()
            if not file_data:
                continue
            if file_data.get('type') in {'photo', 'document'} and self._is_deleted_media(result.path):
                weibo_logger.info("和谐的内容：" + result.path)
                continue
            files.append(file_data)
        if not files:
            return None
        post_data = self.base_dispatch_data()
        post_data['files'] = files[0] if len(files) == 1 else files
        return post_data

    @staticmethod
    def _is_deleted_media(path: str) -> bool:
        """检查下载后的媒体是否命中微博和谐文件特征。"""
        try:
            with open(path, mode='rb') as file_obj:
                return bytes2md5(file_obj.read()) in del_file
        except OSError:
            return False

    @property
    def create_time(self):
        """返回当前微博应参与排序和增量判断的时间。"""

        def standardize_weibo_date(created_at: str):
            """将微博时间字符串解析为本地 datetime。"""
            created_at = created_at.replace("+0800 ", "")
            return datetime.strptime(created_at, "%c")

        if self.data.get('edit_at'):
            return standardize_weibo_date(self.data['edit_at'])
        return standardize_weibo_date(self.data['created_at'])

    def start(self, expected_userid: str | None = None):
        """判断微博是否应进入统一发送流水线，并返回用于日志的类型描述。"""
        weibo_dict = self.data
        if weibo_dict.get('mblog_vip_type') == 1:
            return False, self.__str__() + ' V+微博'
        if isinstance(weibo_dict.get('retweeted_status'), dict) and isinstance(
                weibo_dict.get('retweeted_status', {}).get('user'), dict):
            return False, self.__str__() + ' 转发微博'
        if expected_userid and weibo_dict.get('user', {}).get('idstr') != expected_userid:
            return False, self.__str__() + ' 转发微博'
        if weibo_dict.get('mix_media_info', {}).get('items'):
            return True, self.__str__() + ' 图片视频微博'
        if isinstance(weibo_dict.get('pic_ids'), list) and weibo_dict.get('pic_ids'):
            return True, self.__str__() + ' 图片微博'
        media_info = (weibo_dict.get('page_info') or {}).get('media_info') or {}
        if any(media_info.get(key) for key in VIDEO_URL_KEYS):
            return True, self.__str__() + ' 视频微博'
        return False, self.__str__() + ' 文字微博'


def get_weibo_data(weibo_link):
    weibo_id = weibo_link.split('/')[-1]
    try:
        response = requests.get(f'{WEIBO_API_BASE_URL}/ajax/statuses/show',
                                params={'id': weibo_id, 'locale': 'zh-CN'},
                                headers=weibo_header)
        data = response.json()
    except Exception as e:
        weibo_logger.error("获取微博信息失败：" + weibo_link)
        log_error(weibo_link, '获取微博失败')
        return False
    if 'message' in data and (data['message'] == '暂无查看权限' or data['message'] == '该微博不存在'):
        weibo_logger.error(data['message'] + "\t" + weibo_link)
        return True
    elif 'message' in data and (data['message'] == '访问频次过高，请稍后再试'):
        time.sleep(90)
    elif data.get('message') == "该内容请至手机客户端查看":
        print(data['message'])
        return True
    data['weibo_url'] = weibo_link
    return data


def build_weibo_post(
        weibo_url: str,
        weibo_data: Dict[str, Any] | None = None,
        userid: str | None = None,
        username: str | None = None,
):
    """构造单条微博 Post，兼容在线获取和本地 JSON 回退。"""
    if weibo_data is None:
        weibo_data = get_weibo_data(weibo_url)
        if weibo_data is False:
            return False
        if weibo_data is True:
            return 'skip'

    if 'user' not in weibo_data:
        json_path = find_file_by_name(WEIBO_JSON_ROOT, f'{weibo_url.split("/")[-1]}.json')
        if not json_path:
            return False
        with open(json_path, encoding='utf-8') as file_obj:
            weibo_data = json.load(file_obj)

    following = Following(
        userid or weibo_data['user']['idstr'],
        username or weibo_data['user']['screen_name'],
        None,
    )
    return WeiboPost(following, weibo_data)


def handle_weibo(weibo_index, weibo_url, weibo_data=None, userid=None, username=None):
    """兼容旧调用方式，处理单条微博的下载与发送。"""
    post = build_weibo_post(weibo_url, weibo_data=weibo_data, userid=userid, username=username)
    if post is False or post == 'skip':
        return post

    expected_userid = None if username == 'favorite' else userid
    should_process, start_message = post.start(expected_userid)
    weibo_logger.info(f"{weibo_index}\t{start_message}")
    if not should_process:
        return 'skip'
    return dispatch_post(post, weibo_logger)


class WeiboScrapy(BasePlatform):
    """微博平台抓取器。

    既作为平台注册入口，也作为“单个关注账号”的执行器。
    一个实例只处理一个 following 的内容抓取、过滤和发送。
    """

    name = 'weibo'
    content_name = '微博'
    exclude_equal_latest_time = False

    def __init__(self, following: Following):
        self.scraping = following
        self.username = following.username
        self.userid = following.userid
        self.last_one_time = following.latest_time or datetime(2000, 12, 12, 12, 12, 12)
        self.logger = weibo_logger
        self.post: list[WeiboPost] = []

    def get_post_from_api(self) -> None:
        """实时请求微博接口，抓取当前账号的新微博。"""
        self.post = []
        page = 1
        since_id = ''
        KEEP = True
        while KEEP:
            if self.username == 'favorite':
                try:
                    response = requests.get(
                        f"{WEIBO_API_BASE_URL}/ajax/statuses/likelist",
                        params={
                            'uid': self.userid,
                            'page': page,
                            'count': 50,
                            'since_id': since_id,
                        },
                        headers=cookie_headers,
                        timeout=30,
                    )
                    info = response.json()
                except Exception as exc:
                    weibo_logger.error(f'{self.username} 获取喜欢微博失败: {exc}')
                    break
                if info.get('ok') != 1:
                    weibo_logger.warning(f'{self.username} 喜欢微博接口返回异常: {info}')
                    break
                mblogs = info.get('data', {}).get('list') or []
                if not mblogs:
                    break
                for weibo_info in mblogs:
                    if 'user' not in weibo_info:
                        continue
                    weibo_id = str(weibo_info.get('idstr') or weibo_info.get('id') or '')
                    if not weibo_id:
                        continue
                    weibo = WeiboPost(self.scraping, weibo_info)
                    self.post.append(weibo)
                since_id = info.get('data', {}).get('since_id', '')
                scrapy_info = f'{self.username} 获取第{page}页完成，有{len(mblogs)}个微博, 共获取 {len(self.post)} 个微博'
                if len(self.post) >= SCRAPY_FAVORITE_LIMIT:
                    scrapy_info += ",获取新喜欢完成。"
                    weibo_logger.info(scrapy_info)
                    break
                if not since_id:
                    scrapy_info += ",没有新喜欢了。"
                    weibo_logger.info(scrapy_info)
                    break
                weibo_logger.info(scrapy_info)
                page += 1
                continue
            else:
                try:
                    response = requests.get(
                        f"{WEIBO_API_BASE_URL}/ajax/statuses/mymblog",
                        params={"uid": self.userid, "page": page, "feature": 0},
                        headers=headers,
                        timeout=30,
                    )
                    info = response.json()
                except Exception as exc:
                    weibo_logger.error(f'{self.username} 获取主页微博失败: {exc}')
                    break

                if info.get('ok') == 0 and info.get('msg') == '请求过于频繁':
                    weibo_logger.info(f'{info.get("msg")}')
                    time.sleep(60)
                    continue
                if info.get('ok') == 0 and info.get('msg') == "这里还没有内容":
                    break
                if info.get('ok') == -100:
                    weibo_logger.info('需要验证')
                    break
                if not ('data' in info and 'list' in info['data']):
                    weibo_logger.warning(f'{self.username} 微博主页接口返回异常: {info}')
                    break

                mblogs = info['data']['list'] or []
                if not mblogs:
                    break
                since_id = info.get('data', {}).get('since_id', '')
                for weibo_info in mblogs:
                    weibo_id = str(weibo_info.get('idstr') or weibo_info.get('id') or '')
                    if not weibo_id:
                        continue
                    weibo = WeiboPost(self.scraping, weibo_info)
                    weibo.save_json()
                    self.post.append(weibo)
                    if not weibo.is_top and weibo.create_time < self.scraping.latest_time:
                        KEEP = False
                scrapy_info = f'{self.username} 获取第{page}页完成，有{len(mblogs)}个微博, 共获取 {len(self.post)} 个微博'
                if since_id == '' or (not KEEP):
                    scrapy_info += "，获取新微博完成。"
                    weibo_logger.info(scrapy_info)
                    break
                else:
                    weibo_logger.info(scrapy_info)
                page += 1

    def get_post_from_local(self) -> None:
        """从本地 JSON 缓存恢复当前账号的微博列表。"""
        json_dir = get_platform_json_dir('weibo', self.username)
        if not os.path.isdir(json_dir):
            weibo_logger.warning(f'{self.username} 本地 JSON 目录不存在: {json_dir}')
            return

        for filename in os.listdir(json_dir):
            if not filename.endswith('.json'):
                continue
            json_path = os.path.join(json_dir, filename)
            try:
                with open(json_path, encoding='utf-8') as json_file:
                    weibo_data = json.load(json_file)
            except (OSError, json.JSONDecodeError) as exc:
                weibo_logger.warning(f'读取本地微博 JSON 失败: {json_path} {exc}')
                continue

            if 'user' not in weibo_data:
                weibo_logger.warning(f'本地微博 JSON 缺少用户字段: {json_path}')
                continue
            self.post.append(WeiboPost(self.scraping, weibo_data))

        weibo_logger.info(f'{self.username} 从本地 JSON 获取到 {len(self.post)} 个微博')

    def should_sort_filtered_posts(self) -> bool:
        return self.scraping.username != 'favorite'

    @classmethod
    def run(cls, argv=None):
        return main(argv)


def main(argv=None):
    return run_platform_main(
        'weibo',
        weibo_logger,
        build_following=lambda raw: Following(*raw),
        run_one=lambda following, sent_urls, args: WeiboScrapy(following).start(
            sent_urls,
            use_local_json=args.local_json,
        ),
        argv=argv,
    )


if __name__ == '__main__':
    main()
