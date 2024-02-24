from os.path import splitext, basename, getsize
from urllib.parse import urlparse
from utils import *

instagram_headers = {
    'authority': 'www.instagram.com',
    'accept': '*/*',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'cache-control': 'no-cache',
    'content-type': 'application/x-www-form-urlencoded',
    'cookie': 'ig_did=AFC567FD-6D72-4DBB-BB97-CBA38A9863E3; datr=TGKTZcw9b3j5B1PvNLiMRCRc; mid=ZZe3vQALAAH-Wx3ygnwfh539E6uU; ig_nrcb=1; dpr=1.3541666269302368; ps_n=0; ps_l=0; csrftoken=qs9rnw9s97GwtbfUDVXYz0eNVz3u2CkR; ds_user_id=56449351710; shbid="17455\\05456449351710\\0541740028817:01f7383c9710dfda197bc7a509815b915f739ea76d22c64c7ee2e72b40353248a2d9ec3f"; shbts="1708492817\\05456449351710\\0541740028817:01f7eae0e6b1cd257894bf4b0388eb0e6508aa456e99040d3b8f7f8bd3a3e10a8d36409d"; sessionid=56449351710%3AyQTNaU3RCjHkSc%3A15%3AAYeC6SLNVBRagnyo9K4u9iK7F0aoqU_63m9sh7usmA; rur="NAO\\05456449351710\\0541740114464:01f739ef083e09df200f50174fd4535747da19de5f66666675b4d6bc00347609b934fe34"',
    'dpr': '1.35417',
    'origin': 'https://www.instagram.com',
    'pragma': 'no-cache',
    'referer': 'https://www.instagram.com/p.i.n.k02/',
    'sec-ch-prefers-color-scheme': 'light',
    'sec-ch-ua': '"Not A(Brand";v="99", "Microsoft Edge";v="121", "Chromium";v="121"',
    'sec-ch-ua-full-version-list': '"Not A(Brand";v="99.0.0.0", "Microsoft Edge";v="121.0.2277.128", "Chromium";v="121.0.6167.184"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-model': '""',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua-platform-version': '"15.0.0"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
    'viewport-width': '1883',
    'x-asbd-id': '129477',
    'x-csrftoken': 'qs9rnw9s97GwtbfUDVXYz0eNVz3u2CkR',
}
instagram_logger = MyLogger('instagram', 'scrapy_instagram', mode='a')
graphql_url = 'https://www.instagram.com/api/graphql'
fb_dtsg = 'NAcOHs17aPsstlXPht3t8RvIdfHPQkgDsuacIVlsvKPHUxYzlOa_BDA:17843691127146670:1708225385'


class Profile:
    def __init__(self, pk, username, scrapy_type, latest_time):
        self.pk = pk
        self.username = username
        self.scrapy_type = scrapy_type
        if latest_time is None or latest_time == '':
            self.latest_time = datetime(2000, 12, 12, 12, 12, 12)
        else:
            self.latest_time = datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")
        self.url = 'https://www.instagram.com/' + self.username


class Post:
    def __init__(self, node):
        self.node = node
        self.shortcode = self.node['shortcode'] if 'shortcode' in self.node else self.node['code']
        self.caption = node['caption']
        self.url = 'https://www.instagram.com/p/' + self.shortcode
        self.owner_username = node['owner']['username']
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
        r = requests.post(graphql_url, headers=instagram_headers, data=payload_data)
        r.raise_for_status()
    except Exception as e:
        print(e)
    else:
        return r


def get_post_detail(shortcode):
    if 'instagram' in shortcode:
        shortcode = shortcode.split('/')[4]
    variables = {"shortcode": shortcode}
    data = {
        'fb_dtsg': fb_dtsg,
        'fb_api_caller_class': 'RelayModern',
        'fb_api_req_friendly_name': 'PolarisPostRootQuery',
        'variables': json.dumps(variables),
        'server_timestamps': 'true',
        'doc_id': '6845264215599326',
    }
    response = graphql_request(data)
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
    print(media.url)
    r = requests.get(media.url, headers=download_header, stream=True, timeout=30)
    if r.status_code == 200:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, mode='wb') as f:
            f.write(r.content)
        size = getsize(save_path)
        instagram_logger.info('  ' + save_path + "\t" + convert_bytes_to_human_readable(size))
        return size, save_path
    else:
        instagram_logger.error("download get error " + media.post.url + " " + media.filename)
        return size, save_path


def handler_post(post):
    wait_send = []
    post_data = {
        'username': post.owner_username,
        'nickname': post.owner_username,
        'url': post.url,
        'userid': post.owner_pk,
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
    r = request_webhook('/main', post_data, instagram_logger)
    return r


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
