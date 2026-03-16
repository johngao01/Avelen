from __future__ import annotations

import json
import sys
import time
import urllib.parse
from datetime import datetime as dt
from re import sub

import requests
from lxml import etree
from functools import reduce
from typing import Any
from loguru import logger
from core.utils import *
from pydash import get
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
from core.platform import BasePlatform
from core.following import FollowUser
from core.post import BasePost, MediaItem
from core.downloader import Downloader
from core.database import *
from core.scrapy_runner import run_followings, prepare_followings
from core.settings import is_no_send_mode

BASE_DIR = Path(__file__).resolve().parent.parent
COOKIE_DIR = BASE_DIR / 'cookies'
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 初始化 Rich 控制台
console = Console()
logger.remove()
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
)
logger.add(
    str(LOG_DIR / 'scrapy_bilibili.log'),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="DEBUG",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
    encoding="utf-8",
    filter=lambda record: record["extra"].get("name") == "scrapy_bilibili"
)
Day = dt(2000, 1, 1)
scrapy_logger = logger.bind(name="scrapy_bilibili")
save_dir = '/root/download/bilibili'
json_dir = '/root/download/bilibili/json/'
os.makedirs(json_dir, exist_ok=True)
cookies_file = str(COOKIE_DIR / 'bl.txt')
with open(cookies_file, mode='r', encoding='utf8') as cookie_file:
    cookies_netscape = cookie_file.read()
    cookies_list = []
    cookies_dict = {}
    for line in cookies_netscape.split("\n"):
        line = line.strip()

        # 跳过注释和空行
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("#HttpOnly_.bilibili.com"):
                pass
            else:
                continue

        parts = line.split("\t")

        # Netscape 标准应有 7 列
        if len(parts) != 7:
            continue

        name = parts[5]
        value = parts[6]
        cookies_dict[name.strip()] = value.strip()
        cookies_list.append(f"{name}={value}")
    cookies_str = ";".join(cookies_list)

# WBI 签名用的混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]


class VideoDownloader:
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.total_size = 0
        self.final_filename = ""

        # 定义 Rich 进度条样式 (现代、简洁、带渐变感)
        self.progress = Progress(
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
        self.task_id = None

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

    def print_final_report(self):
        """下载完成后的单行精简输出"""
        if not self.end_time or not self.start_time:
            return

        duration = self.end_time - self.start_time
        speed = self.total_size / duration if duration > 0 else 0
        abspath = os.path.abspath(self.final_filename)

        # 核心输出逻辑：一行展示所有信息，不同颜色标记
        console.print(
            f"{dt.now().strftime("%Y-%m-%d %H:%M:%S")} | INFO |\t[white][/white][cyan]{abspath}[/cyan] "
            f"[white][/white][green]{convert_bytes_to_human_readable(self.total_size)}[/green] "
            f"[white][/white][yellow]{convert_bytes_to_human_readable(speed)}/s[/yellow] "
            f"[white][/white][magenta]{duration:.2f}s[/magenta]"
        )


class Following(FollowUser):
    """B站关注对象（复用统一 FollowUser）。"""

    def __init__(self, userid, username, latest_time: str):
        user = FollowUser.from_db_row(userid, username, latest_time)
        super().__init__(user.userid, user.username, user.latest_time)
        self.user_id = user.userid


class Post(BasePost):
    def __init__(self, node):
        self.node = node
        self.dynamic_type = node.get("type", "")
        self.id_str = node.get("id_str", "")
        self.basic = node.get("basic", {})
        self.modules = node.get("modules", {})
        self.author = self.modules.get("module_author", {})
        self.author_name = self.author.get("name", "")
        self._bound_url = None
        super().__init__(
            platform='bilibili',
            post_id=self.id_str,
            user_id=str(node.get('user_id', '')),
            username=node.get('username', self.author_name),
            nickname=self.author_name or node.get('username', ''),
            url=self.url or '',
            text_raw='',
            create_time=self.pub_time,
        )

    def save_json(self):
        """
        将post数据存储在本地保存为json文件
        :return:
        """
        json_path = os.path.join(json_dir, "Dynamic_" + self.id_str + '.json')
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, mode='w', encoding='utf8') as json_write:
            json.dump(self.node, json_write, ensure_ascii=False, indent=4)

    @property
    def pub_time(self):
        pub_time = self.author.get("pub_ts", "")
        return dt.fromtimestamp(int(pub_time))

    def is_top(self):
        module_tag = self.modules.get("module_tag", {})
        if module_tag:
            text = module_tag.get("text", "")
            if text == '置顶':
                return True
            else:
                return False
        return False

    def get_video_id(self):
        if self.dynamic_type == "DYNAMIC_TYPE_AV":
            module_dynamic = self.modules.get("module_dynamic", {})
            major = module_dynamic.get("major", {})
            archive = major.get("archive", {})
            vid = archive.get("bvid", "")
            return vid
        return None

    def get_opus_id(self):
        if self.dynamic_type == "DYNAMIC_TYPE_DRAW":
            return self.id_str
        return None

    @property
    def url(self):
        if self._bound_url:
            return self._bound_url
        jump_url = self.basic.get("jump_url")
        if jump_url:
            return jump_url
        if self.dynamic_type == "DYNAMIC_TYPE_AV":
            return f"https://t.bilibili.com/{self.id_str}"
        elif self.dynamic_type == "DYNAMIC_TYPE_DRAW":
            return f'https://www.bilibili.com/opus/{self.id_str}'
        else:
            return None

    @url.setter
    def url(self, value):
        self._bound_url = value

    def info(self):
        return f"{self.dynamic_type} {self.pub_time} {self.url}"

    @property
    def badge_text(self):
        if get(self.node, 'basic.is_only_fans'):
            return '充电专属'
        text = get(self.modules, 'module_dynamic.major.archive.badge.text')
        return text

    def bind_context(self, scraping: Following | None = None, api: 'BilibiliAPI' | None = None):
        if scraping is not None:
            self.username = scraping.username
            self.user_id = str(scraping.user_id)
        self.nickname = get(self.author, 'name') or self.username
        self.url = self.url or ''
        if self.dynamic_type == "DYNAMIC_TYPE_DRAW":
            self.text_raw = self._resolve_draw_desc(api)
        else:
            self.text_raw = self._resolve_video_title()
        return self

    def build_media_items(self) -> list[MediaItem]:
        if self.dynamic_type == "DYNAMIC_TYPE_AV":
            title = self._safe_fragment(self._resolve_video_title(), limit=80) or self.get_video_id() or self.id_str
            return [MediaItem(
                url=f'https://www.bilibili.com/video/{self.get_video_id()}',
                media_type='video',
                filename_hint=os.path.join(self.username, f"{self.get_video_id()}_{title}.mp4"),
                referer=self.url,
                ext='mp4',
                index=1,
            )]
        if self.dynamic_type == "DYNAMIC_TYPE_DRAW":
            items = []
            for index, item in enumerate(get(self.node, 'modules.module_dynamic.major.draw.items') or [], start=1):
                src = item.get('src')
                if not src:
                    continue
                ext = src.split('?')[0].split('.')[-1]
                filename = f"{self.id_str}_{self._safe_fragment(self.text_raw, limit=30)}_{index}.{ext}"
                items.append(MediaItem(
                    url=src,
                    media_type='photo',
                    filename_hint=os.path.join(self.username, filename),
                    referer=self.url,
                    ext=ext,
                    index=index,
                ))
            return items
        return []

    def to_dispatch_data(self, downloaded_files) -> dict | None:
        files = [result.to_dispatch_file() for result in downloaded_files if result.to_dispatch_file()]
        if not files:
            return None
        post_data = self.base_dispatch_data()
        post_data['files'] = files[0] if len(files) == 1 else files
        return post_data

    def _resolve_video_title(self):
        return get(self.modules, 'module_dynamic.major.archive.title') or get(self.node, 'describe') or ''

    def _resolve_draw_desc(self, api: BilibiliAPI | None = None):
        desc = get(self.node, 'describe') or ''
        if desc or api is None:
            return desc
        opus_response = api.session.get(f'https://www.bilibili.com/opus/{self.id_str}')
        if opus_response.status_code == 200:
            tree = etree.HTML(opus_response.text)
            result = tree.xpath('//div[@class="opus-module-content opus-paragraph-children"]//span/text()')
            if result:
                desc = result[0]
                self.node['describe'] = desc
                self.save_json()
        else:
            scrapy_logger.warning(f"获取 {self.url} 的 html 内容失败")
        return desc

    @staticmethod
    def _safe_fragment(text: str, limit=30):
        text = text or ''
        if len(text) > limit:
            text = text[:limit]
        text = sub('[\\\\/:*?"<>|\n]', "", text)
        return text or 'post'


class BilibiliAPI:
    """B站 API 客户端"""

    def __init__(self, sessdata: str = "", bili_jct: str = "", buvid3: str = "", dedeuserid: str = "",
                 all_cookies: dict = None):
        """
        初始化 API 客户端

        Args:
            sessdata: SESSDATA cookie
            bili_jct: bili_jct cookie
            buvid3: buvid3 cookie
            dedeuserid: DedeUserID cookie
            all_cookies: 所有 cookies 字典（可选，直接设置全部 cookies）
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com",
        })

        # 如果提供了全部 cookies，直接设置
        if all_cookies:
            for key, value in all_cookies.items():
                self.session.cookies.set(key, value, domain=".bilibili.com")
        else:
            # 设置单独的 cookies
            if sessdata:
                self.session.cookies.set("SESSDATA", sessdata, domain=".bilibili.com")
            if bili_jct:
                self.session.cookies.set("bili_jct", bili_jct, domain=".bilibili.com")
            if buvid3:
                self.session.cookies.set("buvid3", buvid3, domain=".bilibili.com")
            if dedeuserid:
                self.session.cookies.set("DedeUserID", dedeuserid, domain=".bilibili.com")

        # WBI 密钥缓存
        self._img_key = ""
        self._sub_key = ""

    def _get_mixin_key(self, orig: str) -> str:
        """生成混淆后的密钥"""
        return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, '')[:32]

    def _get_wbi_keys(self) -> tuple[str, str]:
        """获取 WBI 签名所需的 img_key 和 sub_key"""
        if self._img_key and self._sub_key:
            return self._img_key, self._sub_key

        resp = self.session.get("https://api.bilibili.com/x/web-interface/nav")
        data = resp.json()

        if data["code"] != 0:
            raise Exception(f"获取 WBI 密钥失败: {data['message']}")

        img_url = data["data"]["wbi_img"]["img_url"]
        sub_url = data["data"]["wbi_img"]["sub_url"]

        # 从 URL 中提取密钥
        self._img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        self._sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]

        return self._img_key, self._sub_key

    def _sign_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """对请求参数进行 WBI 签名"""
        img_key, sub_key = self._get_wbi_keys()
        mixin_key = self._get_mixin_key(img_key + sub_key)

        # 添加时间戳
        params["wts"] = int(time.time())

        # 按 key 排序
        params = dict(sorted(params.items()))

        # 过滤特殊字符并 URL 编码
        query = urllib.parse.urlencode(params)

        # 计算签名
        w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
        params["w_rid"] = w_rid

        return params

    def get_update_dynamics(self, scraping: Following) -> list[Post]:
        dynamics = []
        offset = ''
        page = 1
        scrapy_logger.info(f"开始获取 {scraping.username} 截至到 {scraping.latest_time} 的动态，"
                           f"它的主页是：https://space.bilibili.com/{scraping.user_id}/dynamic")
        while True:
            params = {"host_mid": scraping.user_id, "offset": offset}
            resp = self.session.get(
                "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
                params=params
            )
            data = resp.json()
            if data["code"] != 0:
                scrapy_logger.error(f"获取UP主动态失败: {data['message']}")
                return dynamics
            if not data['data']['has_more']:
                return dynamics
            offset = data['data']['offset']
            total = len(data["data"]['items'])
            page_post = []
            for item in data["data"]['items']:
                item['user_id'] = scraping.user_id
                item['username'] = scraping.username
                post = Post(item)
                page_post.append(post)
                post.save_json()
                if post.pub_time <= scraping.latest_time:
                    if post.is_top():
                        continue
                    return dynamics
                else:
                    dynamics.append(post)
            page_post = sorted(page_post, key=lambda x: x.pub_time)
            scrapy_logger.info(
                f"第 {page} 页获取到 {total} 个动态, {page_post[-1].pub_time} --> {page_post[0].pub_time} , 一共获取到 {len(dynamics)} 个动态")
            time.sleep(2)
            page += 1


def handler_video(dynamic: Post, video_url, username, index):
    scrapy_logger.info(f"{index} {dynamic.info()}")
    if dynamic.badge_text == '充电专属':
        scrapy_logger.info("\t充电专属内容，跳过处理")
        skip_url(video_url)
        return None
    dynamic.username = username
    dynamic.url = video_url
    dynamic.bind_context()
    downloader = Downloader(logger=scrapy_logger)
    return dynamic.to_dispatch_data(downloader.download_post(dynamic))


def handler_opus(dynamic: Post, url, scraping, index, api: BilibiliAPI):
    scrapy_logger.info(f"{index} {dynamic.info()}")
    if dynamic.badge_text == '充电专属':
        scrapy_logger.info("\t充电专属内容，跳过处理")
        skip_url(url)
        return None
    dynamic.url = url
    dynamic.bind_context(scraping, api)
    downloader = Downloader(logger=scrapy_logger)
    return dynamic.to_dispatch_data(downloader.download_post(dynamic))


def skip_url(url):
    with open('../bilibili_skip.txt', 'a') as f:
        f.write(f"失败跳过的 {url}\n")


def from_local_json(scraping: Following):
    dynamics = []
    scrapy_logger.info(f"从本地json文件获取 {scraping.username} 的动态")
    for root, dirs, files in os.walk(json_dir):
        for file in files:
            path = os.path.join(root, file)
            if file.startswith("Dynamic") and file.endswith(".json"):
                with open(path, 'r') as f:
                    json_data = json.load(f)
                if 'user_id' in json_data and json_data['user_id'] == scraping.user_id:
                    post = Post(json_data)
                    dynamics.append(post)
    return dynamics


def find_download_file(username: str, file_id: str):
    files = []
    user_dir = os.path.join(save_dir, username)
    if not os.path.exists(user_dir):
        return files
    else:
        for file in os.listdir(user_dir):
            if file_id in file:
                files.append(os.path.join(user_dir, file))
    return files


def handle_dispatch_result(result, logger, url: str, on_success_update=None, on_failure_update=None) -> str:
    if getattr(result, 'status_code', None) == 200:
        if not is_no_send_mode():
            download_log(result)
            rate_control(result, logger)
            if on_success_update:
                on_success_update()
        return 'success'
    if isinstance(result, str) and 'skip' in result:
        return 'skip'
    if on_failure_update:
        on_failure_update()
    error_text = getattr(result, 'status_code', result)
    log_error(url, error_text)
    logger.error(f"处理 {url} 失败")
    return 'failure'


def start(scraping: Following, api: BilibiliAPI, send_url, use_local_json=False):
    if not use_local_json:
        dynamics = api.get_update_dynamics(scraping)
    else:
        dynamics = from_local_json(scraping)
    dynamics = sorted(dynamics, key=lambda x: x.pub_time)
    total = len(dynamics)
    for idx, dynamic in enumerate(dynamics, start=1):
        if dynamic.dynamic_type == 'DYNAMIC_TYPE_AV':
            url = f'https://www.bilibili.com/video/{dynamic.get_video_id()}'
            if url in send_url:
                continue
            post_data = handler_video(dynamic, url, scraping.username, f"{idx}/{total}")
        elif dynamic.dynamic_type == 'DYNAMIC_TYPE_DRAW':
            url = f'https://www.bilibili.com/opus/{dynamic.get_opus_id()}'
            if url in send_url:
                continue
            post_data = handler_opus(dynamic, url, scraping, f"{idx}/{total}", api)
        else:
            continue
        if post_data is None:
            continue
        r = request_webhook('/main', post_data, scrapy_logger)
        handle_dispatch_result(
            r,
            scrapy_logger,
            url,
            on_success_update=lambda: update_db(
                scraping.user_id,
                scraping.username,
                dynamic.pub_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        )


def configure_parser(parser):
    parser.add_argument('--local-json', action='store_true', help='从本地 json 目录读取数据，而不是实时抓取')


def main(argv=None):
    args, all_followings = prepare_followings(
        'bilibili',
        default_valid=(1,),
        configure_parser=configure_parser,
        argv=argv,
    )
    api = BilibiliAPI(all_cookies=cookies_dict)
    send_url = get_send_url('bilibili')
    run_followings(
        all_followings,
        build_following=lambda raw: Following(*raw),
        run_one=lambda following: start(following, api, send_url, use_local_json=args.local_json),
        logger=scrapy_logger,
    )


class BilibiliPlatform(BasePlatform):
    name = 'bilibili'
    aliases = ('bili',)

    @classmethod
    def run(cls, argv=None):
        return main(argv)


if __name__ == '__main__':
    main()
