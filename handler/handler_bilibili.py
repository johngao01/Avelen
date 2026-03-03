import sys
import time
import urllib.parse
import shutil
from re import sub
from lxml import etree
from functools import reduce
from typing import Any
from loguru import logger
from tools.utils import *
from yt_dlp import YoutubeDL
from pydash import get

logger.remove()
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
)
logger.add(
    f"../logs/scrapy_bilibili.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="DEBUG",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
    encoding="utf-8",
    filter=lambda record: record["extra"].get("name") == "scrapy_bilibili"
)
Day = datetime(2000, 1, 1)
scrapy_logger = logger.bind(name="scrapy_bilibili")
save_dir = '/root/download/bilibili'
json_dir = '/root/download/bilibili/json/'
os.makedirs(json_dir, exist_ok=True)
cookies_file = '../cookies/bl.txt'
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

# 配置（根据需要调整）
ydl_opts = {
    'logger': scrapy_logger,
    # cookies 文件（Windows 示例路径）
    'cookiefile': cookies_file,
    # 输出模板，便于知道文件保存位置；可按需修改
    # 'outtmpl': r'/root/download/bilibili/%(uploader)s/%(id)s_%(title)s.%(ext)s',
    # 合并视频+音频
    'format': 'bestvideo+bestaudio',
    'fragment_retries': 10,
    'retries': 10,
    # 忽略可跳过的错误（下载失败时继续后续条目）
    'ignoreerrors': True,
    # 只处理播放列表中的第 1-5 条（你也可以改为 '1-5'）
    # 让 yt-dlp 为每个条目写 .info.json
    'writeinfojson': True,
    # 不要用扁平提取（如果你需要完整 metadata，确保不要设置 flat-playlist）
    'extract_flat': True,
    # 倒序处理，先处理最早的作品
    'playlist_reverse': True
}
# WBI 签名用的混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]


class Following:
    def __init__(self, userid, username, latest_time: str):
        self.user_id = userid
        self.username = username
        if latest_time is None or latest_time == '':
            self.latest_time = datetime(2000, 12, 12, 12, 12, 12)
        else:
            self.latest_time = datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")


class Post:
    def __init__(self, node):
        self.node = node
        self.dynamic_type = node.get("type", "")
        self.id_str = node.get("id_str", "")
        self.basic = node.get("basic", {})
        self.modules = node.get("modules", {})
        self.author = self.modules.get("module_author", {})
        self.author_name = self.author.get("name", "")

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
        return datetime.fromtimestamp(int(pub_time))

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
        jump_url = self.basic.get("jump_url")
        if jump_url:
            return jump_url
        if self.dynamic_type == "DYNAMIC_TYPE_AV":
            return f"https://t.bilibili.com/{self.id_str}"
        elif self.dynamic_type == "DYNAMIC_TYPE_DRAW":
            return f'https://www.bilibili.com/opus/{self.id_str}'
        else:
            return None

    def info(self):
        return f"{self.dynamic_type} {self.pub_time} {self.url}"

    @property
    def badge_text(self):
        text = get(self.modules, 'module_dynamic.major.badge.text')
        return text


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
            offset = data['data']['offset']
            total = len(data["data"]['items'])
            scrapy_logger.info(f"第 {page} 页获取到 {total} 个动态")
            for item in data["data"]['items']:
                item['user_id'] = scraping.user_id
                item['username'] = scraping.username
                post = Post(item)
                post.save_json()
                if post.pub_time <= scraping.latest_time:
                    if post.is_top():
                        continue
                    return dynamics
                else:
                    dynamics.append(post)
            time.sleep(2)
            page += 1


def handler_video(dynamic: Post, video_url, username, index):
    scrapy_logger.info(f"{index} {dynamic.info()}")
    if dynamic.badge_text == '充电专属':
        scrapy_logger.info("\t充电专属内容，跳过处理")
        skip_url(video_url)
    ydl_opts.update({'outtmpl': rf'/root/download/bilibili/{username}/%(id)s_%(title)s.%(ext)s'})
    with YoutubeDL(ydl_opts) as ydl:
        # 这种方式比 process_info 更可控
        video = ydl.extract_info(video_url, download=True)
        if not video:
            scrapy_logger.error(f"获取 {video_url} 数据失败")
            return 'error'
    title = get(video, 'fulltitle')
    post_time = get(video, 'timestamp') or get(video, 'epoch')
    if post_time is None:
        scrapy_logger.error(f"获取 {video_url} 数据失败")
    post_time = datetime.fromtimestamp(post_time)
    post_data = {
        'username': username,
        'nickname': get(video, 'uploader'),
        'url': video_url,
        'userid': get(video, 'uploader_id'),
        'idstr': get(video, 'id'),
        'mblogid': '',
        'create_time': post_time.strftime('%Y-%m-%d %H:%M:%S'),
        'text_raw': title,
    }
    try:
        expected_path = ydl.prepare_filename(video)
    except Exception:
        expected_path = None
    if os.path.exists(expected_path):
        size = os.path.getsize(expected_path)
        human_readable_size = convert_bytes_to_human_readable(size)
        if size > MAX_VIDEO_SIZE:
            scrapy_logger.info(f"{expected_path} 太大，无法发送。")
            skip_url(video_url)
            return None
        scrapy_logger.info(f"\t{expected_path} {human_readable_size}")
        base = os.path.splitext(expected_path)[0]
        infojson_path = base + '.info.json'
        try:
            shutil.move(infojson_path, '/root/download/bilibili/json/')
        except Exception as e:
            pass
        post_data.update({'files': {'media': expected_path, 'caption': os.path.basename(expected_path),
                                    'type': 'video'}})
        return post_data
    return None


def handler_opus(dynamic: Post, url, scraping, index, api: BilibiliAPI):
    scrapy_logger.info(f"{index} {dynamic.info()}")
    if dynamic.badge_text == '充电专属':
        scrapy_logger.info("\t充电专属内容，跳过处理")
        skip_url(url)
    draw = get(dynamic.node, 'modules.module_dynamic.major.draw.items')
    opus_response = api.session.get(f'https://www.bilibili.com/opus/{dynamic.id_str}')
    if opus_response.status_code == 200:
        tree = etree.HTML(opus_response.text)
        result = tree.xpath('//div[@class="opus-module-content opus-paragraph-children"]//span/text()')
        if result:
            desc = result[0]
            dynamic.node['describe'] = desc
            dynamic.save_json()
        else:
            desc = ''
    else:
        scrapy_logger.warning(f"获取 {url} 的 html 内容失败")
        desc = ''
    if len(desc) > 30:
        desc = sub('[\\\\/:*?"<>|\n]', "", desc[0:30])
    else:
        desc = sub('[\\\\/:*?"<>|\n]', "", desc)
    if draw is None:
        return None
    total = len(draw)
    post_data = {
        'username': scraping.username,
        'nickname': get(dynamic.author, 'name') or scraping.username,
        'url': url,
        'userid': str(scraping.user_id),
        'idstr': dynamic.id_str,
        'mblogid': '',
        'create_time': dynamic.pub_time.strftime('%Y-%m-%d %H:%M:%S'),
        'text_raw': desc,
    }
    files = []
    for idx, item in enumerate(draw, start=1):
        src = item.get('src')
        response = api.session.get(src, stream=True)
        if response.status_code != 200:
            scrapy_logger.error(f"下载 {src} 失败" + f" {response.text}")
            return None
        ext = src.split('.')[-1]
        filename = dynamic.id_str + f"_{desc}_{idx}.{ext}"
        filepath = os.path.join(save_dir, scraping.username, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, mode='wb') as f:
            f.write(response.content)
        file_data = handler_file(filepath, f'{idx}/{total}', scrapy_logger)
        if file_data:
            files.append(file_data)
    post_data.update({'files': files})
    return post_data


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
                    if post.pub_time <= scraping.latest_time:
                        dynamics.append(post)
    return dynamics
