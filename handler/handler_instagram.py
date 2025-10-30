from os.path import splitext, basename, getsize
from urllib.parse import urlparse
from tools.utils import *
import sys
from loguru import logger
import re

logger.remove()
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
)
logger.add(
    f"../logs/scrapy_instagram.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
    encoding="utf-8",
    filter=lambda record: record["extra"].get("name") == "scrapy_instagram"
)
instagram_logger = logger.bind(name="scrapy_instagram")
with open('../cookies/neverblock11.txt', 'r', encoding='utf-8') as f:
    cookies = f.read()


def parse_cookie_header(header):
    pattern = re.compile(r'(?:^|;\s*)([^=;\s]+)=(?:"([^"]*)"|([^;]*))')
    res = {}
    for m in pattern.finditer(header):
        key = m.group(1)
        val = m.group(2) if m.group(2) is not None else (m.group(3) or '')
        # 处理 \ooo 八进制转义
        val = re.sub(r'\\([0-7]{3})', lambda mo: chr(int(mo.group(1), 8)), val)
        val = val.replace('\\"', '"').replace('\\\\', '\\')
        res[key] = val
    return res


parsed = parse_cookie_header(cookies)
csrftoken = parsed.get('csrftoken', '')
logger.info(f"csrftoken: {csrftoken}")
instagram_headers = {
    'accept': '*/*',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,ja;q=0.5',
    'cache-control': 'no-cache',
    'content-type': 'application/x-www-form-urlencoded',
    'origin': 'https://www.instagram.com',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://www.instagram.com/',
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
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0',
    'x-asbd-id': '359341',
    'x-bloks-version-id': 'f4e32caf235c4c3198ceb3d7599c397741599ea3447ec2f785d4575aeb99766b',
    'x-csrftoken': csrftoken,
    'x-fb-friendly-name': 'PolarisProfilePostsQuery',
    'x-fb-lsd': 'FASx-b1QHr26PyPKzuK9UW',
    'x-ig-app-id': '936619743392459',
    'x-root-field-name': 'xdt_api__v1__feed__user_timeline_graphql_connection',
    'cookie': cookies,
}
data = {
    'av': '17841456631306168',
    '__d': 'www',
    '__user': '0',
    '__a': '1',
    '__req': 'g',
    '__hs': '20004.HYP:instagram_web_pkg.2.1..0.1',
    'dpr': '1',
    '__ccg': 'UNKNOWN',
    '__rev': '1017134301',
    '__s': 'f948gm:6gn02x:zry8iy',
    '__hsi': '7423234038434103824',
    '__dyn': '7xeUjG1mxu1syUbFp41twpUnwgU7SbzEdF8aUco2qwJxS0k24o1DU2_CwjE1xoswaq0yE462mcw5Mx62G5UswoEcE7O2l0Fwqo31w9a9wtUd8-U2zxe2GewGw9a361qw8Xxm16wUwtEvw5rCwLyESE7i3vwDwHg2ZwrUdUbGwmk0zU8oC1Iwqo5q3e3zhA6bwIDyUrAwCAxW1oCz8rwHwcOEy',
    '__csr': 'hs2D6iiiMjPAttEmAAJqnYOrFnJGBuJV6rGp4emV5u_KRBVlLFAjy9vUGy4hQKAt95nBGivHWUyF6yF2poxoFAjAZ4CgGFFryppJ2axeifyEym9xi4228y4UOjhFeeAVrVaGFFEO9gHF2Q-8Qm4GUWeyauU9E01dWEkDwe62W6U0F-Eh8mWAU14o2iwdOmhwSpV7e9yE090K1g82u0TU0Au4lG0yia4kmdOwooaA2h6gGl0u97ypJ5ELDmNE2-wYwxiomwiRBl6wXxi2ZwVxGh6w40x6bx-4FE27waK11who4Ajy8pgB0D2oEgi1ew0FEw0liE0mVw',
    '__comet_req': '7',
    'fb_dtsg': 'NAcMqQJme8Zv4-SpU2fRGCLK2EHheAVhpp-SYk847IPcxXyunn0OMBw:17843671327157124:1710762843',
    'jazoest': '26150',
    'lsd': 'IOlBer4tOLe1g3Wezxmxib',
    '__spin_r': '1017134301',
    '__spin_b': 'trunk',
    '__spin_t': '1728356359',
    'qpl_active_flow_ids': '1056839232',
    'fb_api_caller_class': 'RelayModern',
    'fb_api_req_friendly_name': 'LSPlatformGraphQLLightspeedRequestForIGDQuery',
    'variables': '{"deviceId":"e645281c-1c20-4fe2-ab5c-576765e998ed","requestId":0,"requestPayload":"{\\"database\\":1,\\"epoch_id\\":0,\\"last_applied_cursor\\":null,\\"sync_params\\":\\"{\\\\\\"bloks_version\\\\\\":\\\\\\"834a5e272ad60874513e8388fb7e1f1e894653cb45a6b1160396fcd3618ba96b\\\\\\",\\\\\\"full_height\\\\\\":200,\\\\\\"locale\\\\\\":\\\\\\"zh_CN\\\\\\",\\\\\\"preview_height\\\\\\":200,\\\\\\"preview_height_large\\\\\\":400,\\\\\\"preview_width\\\\\\":150,\\\\\\"preview_width_large\\\\\\":300,\\\\\\"scale\\\\\\":1,\\\\\\"snapshot_num_threads_per_page\\\\\\":15}\\",\\"version\\":8700946419928250}","requestType":1}',
    'server_timestamps': 'true',
    'doc_id': '9830436980396988',
}

graphql_url = 'https://www.instagram.com/graphql/query'
if 'instagram_scrapy.py' in sys.argv[0]:
    r = requests.get('https://www.instagram.com', headers=instagram_headers, data=data)
    # 正则表达式查找并捕获token的值
    match = re.search(r'"DTSGInitialData",\[\],\{"token":"([^"]+)"}', r.text)
    if match:
        fb_dtsg = match.group(1)  # 捕获的token值
        instagram_logger.info(f"fb_dtsg value: {fb_dtsg}")
    else:
        instagram_logger.error("fb_dtsg not found")
        exit(1)
else:
    fb_dtsg = ''


class Profile:
    def __init__(self, pk, username, latest_time):
        self.pk = pk
        self.username = username
        if latest_time is None or latest_time == '':
            self.latest_time = datetime(2000, 12, 12, 12, 12, 12)
        else:
            self.latest_time = datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")
        self.url = 'https://www.instagram.com/' + self.pk


class Post:
    def __init__(self, node):
        self.node = node
        self.shortcode = self.node['shortcode'] if 'shortcode' in self.node else self.node['code']
        self.caption = node['caption']
        self.url = 'https://www.instagram.com/p/' + self.shortcode
        self.owner_username = node['owner']['username']
        if 'nickname' in node:
            self.nickname = node['nickname']
        else:
            self.nickname = self.owner_username
        self.owner_pk = node['owner']['pk']
        self.media_id = node['id']
        self.create_time = datetime.fromtimestamp(node['taken_at'])
        self.carousel_media = node.get('carousel_media') or []
        self.video = node.get('video_versions')
        self.preview = node['image_versions2']
        self.pin_info = node.get('timeline_pinned_user_ids')

    @property
    def text(self):
        if self.caption:
            return self.caption['text']
        return ''

    @property
    def media_count(self):
        if len(self.carousel_media) > 1:
            return len(self.carousel_media)
        return 1

    def get_medias(self) -> 'Media':
        if self.media_count == 1:
            if self.video:
                yield Media(largest_media(self.video), self)
            else:
                yield Media(largest_media(self.node['image_versions2']['candidates']), self)
        else:
            for m in self.carousel_media:
                yield Media(largest_media(m['image_versions2']['candidates']), self)

    @property
    def is_pined(self):
        if self.pin_info:
            if self.owner_pk in self.pin_info:
                return True
        return False


class Media:
    def __init__(self, node, post):
        self.post = post
        self.node = node
        self.id = node.get('id')
        self.width = node['width']
        self.height = node['height']
        self.url = node['url']

    @property
    def size(self):
        return self.width, self.height

    @property
    def filename(self):
        name = basename(urlparse(self.url).path)
        if name.endswith('.mp4'):
            filename = splitext(basename(urlparse(self.post.node['image_versions2']['candidates'][0]['url']).path))[0]
            name = filename + '.mp4'
        return name

    @property
    def save_path(self):
        return os.path.join(download_save_root_directory, 'instagram', self.post.owner_username, self.filename)

    @property
    def media_type(self):
        if self.filename.endswith('.mp4'):
            return 'video'
        else:
            return 'photo'


def largest_media(medias):
    total_value = 0
    largest = ''
    for m in medias:
        size = m['height'] + m['width']
        if size > total_value:
            total_value = size
            largest = m
    return largest


def graphql_request(payload_data):
    try:
        rs = requests.post(graphql_url, headers=instagram_headers, data=payload_data)
        rs.raise_for_status()
        return rs.json()
    except Exception as e:
        print(e)
        return None


def get_post_detail(shortcode):
    if 'instagram' in shortcode:
        shortcode = shortcode.split('/')[4]
    variables = {"shortcode": shortcode}
    response = graphql_request({
        'fb_dtsg': fb_dtsg,
        'fb_api_caller_class': 'RelayModern',
        'fb_api_req_friendly_name': 'PolarisPostRootQuery',
        'variables': json.dumps(variables),
        'server_timestamps': 'true',
        'doc_id': '6845264215599326',
    })
    return response.json()


def download_file(media: Media):
    download_header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 '
                      'Safari/537.36 Edg/120.0.0.0',
        'referer': f'https://www.instagram.com/p/{media.post.shortcode}'
    }
    save_path = media.save_path
    size = 0
    if os.path.exists(save_path):
        size = getsize(save_path)
        instagram_logger.info('  ' + save_path + "\t" + convert_bytes_to_human_readable(size))
        return size, save_path
    r = requests.get(media.url, headers=download_header, stream=True, timeout=30)
    if r.status_code == 200:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        save_content(save_path, r)
        size = getsize(save_path)
        instagram_logger.info('  ' + save_path + "\t" + convert_bytes_to_human_readable(size))
        return size, save_path
    else:
        instagram_logger.error("download get error " + media.post.url + " " + media.filename)
        return size, save_path


def handler_post(post):
    wait_send = []
    post_data = {
        'username': post.nickname,
        'nickname': post.owner_username,
        'url': post.url,
        'userid': post.owner_username,
        'idstr': post.shortcode,
        'mblogid': post.media_id,
        'create_time': post.create_time.strftime("%Y-%m-%d %H:%M:%S"),
        'text_raw': post.text,
    }
    for media in post.get_medias():
        size, save_path = download_file(media)
        if size:
            file_data = {
                'media': save_path,
                'caption': media.filename,
                'size': size,
                'type': media.media_type
            }
            wait_send.append(file_data)
    if post.media_count != len(wait_send):
        instagram_logger.error(post.url + "所有内容未全部下载")
        return "所有内容未全部下载"
    if len(wait_send) >= 2:
        post_data.update({'files': wait_send})
    elif len(wait_send) == 1:
        post_data.update({'files': wait_send[0]})
    result = request_webhook('/main', post_data, instagram_logger)
    return result


def save_json(post: Post):
    """
    将post数据存储在本地保存为json文件
    :return:
    """
    json_path = os.path.join(download_save_root_directory, 'instagram', 'json', post.owner_username,
                             post.shortcode + '.json')
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, mode='w', encoding='utf8') as json_write:
        json.dump(post.node, json_write, ensure_ascii=False, indent=4)
