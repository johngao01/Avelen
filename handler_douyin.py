import os.path
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import md5
from re import sub
from time import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from utils import *

scrapy_logger = MyLogger('douyin', 'scrapy_douyin', mode='a')

with open('cookies.txt', mode='r', encoding='utf8') as cookie_file:
    cookies = cookie_file.read()
douyin_headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.183',
    'Cookie': cookies
}

video_aweme_detail_url = 'https://www.douyin.com/aweme/v1/web/aweme/detail/?'
domain = 'https://www.douyin.com/'
video_url = 'https://www.douyin.com/video/'
note_url = 'https://www.douyin.com/note/'
user_url = 'https://www.douyin.com/user/'


class NewXBogus:
    __string = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="
    __array = [None for _ in range(
        48)] + list(range(10)) + [None for _ in range(39)] + list(range(10, 16))
    __canvas = {
        23: 1256363761,
        20: None,
        174: 1256363761,
    }
    __params = {
        23: 14,
        174: 4,
        20: None,
    }
    __index = {
        23: 0,
        174: 1,
        20: None,
    }

    @staticmethod
    def disturb_array(
            a, b, e, d, c, f, t, n, o, i, r, _, x, u, s, l, v, h, g
    ):
        array = [0] * 19
        array[0] = a
        array[10] = b
        array[1] = e
        array[11] = d
        array[2] = c
        array[12] = f
        array[3] = t
        array[13] = n
        array[4] = o
        array[14] = i
        array[5] = r
        array[15] = _
        array[6] = x
        array[16] = u
        array[7] = s
        array[17] = l
        array[8] = v
        array[18] = h
        array[9] = g
        return array

    @staticmethod
    def generate_garbled_1(
            a,
            b,
            e,
            d,
            c,
            f,
            t,
            n,
            o,
            i,
            r,
            _,
            x,
            u,
            s,
            l,
            v,
            h,
            g):
        array = [0] * 19
        array[0] = a
        array[1] = r
        array[2] = b
        array[3] = _
        array[4] = e
        array[5] = x
        array[6] = d
        array[7] = u
        array[8] = c
        array[9] = s
        array[10] = f
        array[11] = l
        array[12] = t
        array[13] = v
        array[14] = n
        array[15] = h
        array[16] = o
        array[17] = g
        array[18] = i
        return "".join(map(chr, map(int, array)))

    @staticmethod
    def generate_num(text):
        return [
            ord(text[i]) << 16 | ord(text[i + 1]) << 8 | ord(text[i + 2]) << 0
            for i in range(0, 21, 3)
        ]

    @staticmethod
    def generate_garbled_2(a, b, c):
        return chr(a) + chr(b) + c

    @staticmethod
    def generate_garbled_3(a, b):
        d = list(range(256))
        c = 0
        f = ""
        for a_idx in range(256):
            d[a_idx] = a_idx
        for b_idx in range(256):
            c = (c + d[b_idx] + ord(a[b_idx % len(a)])) % 256
            e = d[b_idx]
            d[b_idx] = d[c]
            d[c] = e
        t = 0
        c = 0
        for b_idx in range(len(b)):
            t = (t + 1) % 256
            c = (c + d[t]) % 256
            e = d[t]
            d[t] = d[c]
            d[c] = e
            f += chr(ord(b[b_idx]) ^ d[(d[t] + d[c]) % 256])
        return f

    def calculate_md5(self, input_string):
        if isinstance(input_string, str):
            array = self.md5_to_array(input_string)
        elif isinstance(input_string, list):
            array = input_string
        else:
            raise TypeError

        md5_hash = md5()
        md5_hash.update(bytes(array))
        return md5_hash.hexdigest()

    def md5_to_array(self, md5_str):
        if isinstance(md5_str, str) and len(md5_str) > 32:
            return [ord(char) for char in md5_str]
        else:
            return [
                (self.__array[ord(md5_str[index])] << 4)
                | self.__array[ord(md5_str[index + 1])]
                for index in range(0, len(md5_str), 2)
            ]

    def process_url_path(self, url_path):
        return self.md5_to_array(
            self.calculate_md5(self.md5_to_array(self.calculate_md5(url_path)))
        )

    def generate_str(self, num):
        string = [num & 16515072, num & 258048, num & 4032, num & 63]
        string = [i >> j for i, j in zip(string, range(18, -1, -6))]
        return "".join([self.__string[i] for i in string])

    # @run_time
    def generate_x_bogus(
            self,
            query: list,
            version: int,
            code: tuple,
            timestamp: int):
        array = [
            64,
            0.00390625,
            1,
            self.__params[version],
            query[-2],
            query[-1],
            69,
            63,
            *code,
            timestamp >> 24 & 255,
            timestamp >> 16 & 255,
            timestamp >> 8 & 255,
            timestamp >> 0 & 255,
            self.__canvas[version] >> 24 & 255,
            self.__canvas[version] >> 16 & 255,
            self.__canvas[version] >> 8 & 255,
            self.__canvas[version] >> 0 & 255,
            None,
        ]
        zero = 0
        for i in array[:-1]:
            if isinstance(i, float):
                i = int(i)
            zero ^= i
        array[-1] = zero
        garbled = self.generate_garbled_1(*self.disturb_array(*array))
        garbled = self.generate_garbled_2(
            2, 255, self.generate_garbled_3("ÿ", garbled))
        return "".join(self.generate_str(i)
                       for i in self.generate_num(garbled))

    def get_x_bogus(
            self,
            query: dict,
            user_agent: tuple,
            version=23,
            test_time=None):
        timestamp = int(test_time or time())
        query = self.process_url_path(urlencode(query))
        return self.generate_x_bogus(
            query, version, user_agent[self.__index[version]], timestamp)


class Following:
    def __init__(self, userid, username, scrapy_type, latest_time):
        self.user_sec_uid = userid
        self.username = username
        self.scrapy_type = scrapy_type
        if latest_time is None or latest_time == '':
            self.latest_time = datetime(2000, 12, 12, 12, 12, 12)
        else:
            self.latest_time = datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")


class Aweme:
    def __init__(self, following, node: Dict[str, Any]):
        self._node = node
        self.username = following.username
        self.user_sec_uid = following.user_sec_uid
        self.aweme_id = node['aweme_id']
        self.aweme_type = node['aweme_type']
        self.describe = node['desc']
        self.create_time = node['create_time']
        self.is_video = self.judge_is_video()
        self.aweme_info = {
            'data': node,
            'url': self.aweme_url,
            'id': self.aweme_id,
            'create_date': self.create_time.strftime("%Y%m%d"),
            'save_dir': os.path.join(download_save_root_directory, 'douyin'),
            'header': douyin_headers.update({'referer': self.aweme_url})
        }
        self.post_data = {
            'username': self.username,
            'nickname': self._node['author']['nickname'],
            'url': self.aweme_url,
            'userid': self.user_sec_uid,
            'idstr': self.aweme_id,
            'mblogid': '',
            'create_time': self.create_time_str,
            'text_raw': self.describe,
        }
        if self.username == 'favorite':
            self.post_data.update({'userid': self._node['author']['sec_uid']})

    def save_json(self):
        """
        将抖音数据存储在本地保存为json文件
        :return:
        """
        json_path = os.path.join(download_save_root_directory, 'douyin', 'json', self.username, self.aweme_id + '.json')
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, mode='w', encoding='utf8') as json_write:
            data = self._node.copy()
            del data['create_time']
            json.dump(data, json_write, ensure_ascii=False, indent=4)

    @property
    def aweme_url(self):
        if self.is_video:
            return video_url + self.aweme_id
        else:
            return note_url + self.aweme_id

    @property
    def create_time_str(self):
        return self.create_time.strftime("%Y-%m-%d %H:%M:%S")

    def judge_is_video(self):
        if self._node.get('images'):
            return False
        elif self._node.get('image_post_info'):
            return False
        elif self._node.get('image_infos'):
            return False
        else:
            return True

    @property
    def content_type(self):
        if self.is_video:
            return 'video'
        else:
            return 'images'

    def media_info(self):
        if self.is_video:
            return self._node['video']
        else:
            return self._node.get('image_infos') or self._node.get('images') or self._node.get('image_post_info')

    def aweme_video(self) -> 'AwemeMedia':
        return AwemeMedia(self, 1, self._node['video'])

    def aweme_photos(self) -> ['AwemeMedia']:
        medias = []
        for i, image in enumerate(self.media_info(), start=1):
            medias.append(AwemeMedia(self, i, image))
        return medias


class AwemeMedia:
    def __init__(self, media_aweme: Aweme, content_index, node: Optional[Dict[str, Any]] = None):
        self._aweme = media_aweme
        self._node = node
        self.aweme_id = self._aweme.aweme_id
        self.content_index = content_index
        self.username = self._aweme.username
        self.user_sec_uid = self._aweme.user_sec_uid
        self.aweme_url = self._aweme.aweme_url
        self.download_referer = self._aweme.aweme_url
        self.content_type = 'video' if self._aweme.is_video else 'image'

    @property
    def content_id(self):
        if self._aweme.is_video:
            return self._node['play_addr']['uri']
        else:
            if 'uri' in self._node:
                return self._node['uri']
            return self._node['label_large']['uri']

    @property
    def download_url(self):
        if self._aweme.is_video:
            return f'https://aweme.snssdk.com/aweme/v1/play/?video_id={self.content_id}&radio=1080p&line=0'
        else:
            if 'url_list' in self._node:
                return self._node['url_list'][0]
            return self._node['url_list'][0]

    @property
    def save_name(self):
        if len(self._aweme.describe) > 100:
            desc = sub('[\\\\/:*?"<>|\n]', "", self._aweme.describe[0:50])
        else:
            desc = sub('[\\\\/:*?"<>|\n]', "", self._aweme.describe)
        if self._aweme.is_video:
            return self._aweme.aweme_id + "_" + desc + ".mp4"
        else:
            return self._aweme.aweme_id + "_" + desc + "_" + str(self.content_index) + ".jpg"

    def save_path(self):
        if self._aweme.is_video:
            filepath = os.path.join(self._aweme.aweme_info['save_dir'], self.username, self.save_name)
        else:
            filepath = os.path.join(self._aweme.aweme_info['save_dir'], 'images', self._aweme.username,
                                    self.save_name)
        return filepath


def download_media(url, content_type, referer=None, **kwargs):
    if referer:
        douyin_headers.update({'referer': referer})
    try:
        resp = requests.get(url, headers=douyin_headers, **kwargs)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(e)
        raise requests.RequestException
    else:
        if content_type == 'image' and resp.headers['Content-Type'].startswith(content_type):
            return resp
        elif content_type == 'video' and resp.headers['Content-Type'].startswith(content_type):
            return resp
        else:
            return None


def download(media: AwemeMedia, aweme_post_data, logger):
    media_name = media.save_name
    save_path = media.save_path()
    if os.path.exists(save_path):
        with open(save_path, mode='rb') as f:
            media_content = f.read()
        media_size = os.path.getsize(save_path)
    else:
        print(media.download_url)
        while True:
            try:
                download_response = download_media(media.download_url, media.content_type,
                                                   media.download_referer,
                                                   stream=True)
                media_content = download_response.content
                break
            except Exception:
                logger.waring('  '.join([media.download_url, '下载失败，重试']))
                continue
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        result = save_content(save_path, media_content)
        if not result:
            logger.info('  '.join([media.content_id, media_name, media.download_url, '下载失败']))
            return
        media_size = len(media_content)
    human_readable_size = convert_bytes_to_human_readable(media_size)
    if media.content_type == 'video':
        logger.info('  '.join([aweme_post_data['username'], aweme_post_data['url'], aweme_post_data['create_time'],
                               os.path.relpath(save_path, '/root/download/douyin/'), human_readable_size]))
    else:
        logger.info('  '.join([os.path.relpath(save_path, '/root/download/douyin/'), human_readable_size]))
    photo_data = {
        'media': save_path,
        'caption': media_name,
        'size': media_size
    }
    if media_size > MAX_VIDEO_SIZE:
        photo_data.update(
            {'type': 'document', 'send_url': f"{media_name}太大，[请单击我查看]({media.download_url})"})
    elif media_content:
        photo_data.update({'type': 'video'}) if media.content_type == 'video' else photo_data.update({'type': 'photo'})
    return photo_data


def handler_video_douyin(aweme: Aweme):
    aweme_video = aweme.aweme_video()
    media_name = aweme_video.save_name
    save_path = aweme_video.save_path()
    if os.path.exists(save_path):
        with open(save_path, mode='rb') as f:
            video_content = f.read()
        video_size = os.path.getsize(save_path)
    else:
        while True:
            try:
                download_response = download_media(aweme_video.download_url, aweme_video.content_type,
                                                   aweme_video.download_referer,
                                                   stream=True)
                video_content = download_response.content
                break
            except Exception:
                scrapy_logger.warning('  '.join([aweme_video.download_url,'下载失败，重试']))
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        result = save_content(save_path, video_content)
        if not result:
            aweme.post_data.update({'message': f"获取[抖音视频]({aweme.aweme_info['url']})失败"})
            r = request_webhook('/send_message', aweme.post_data, scrapy_logger)
            return r
        video_size = len(video_content)
    human_readable_size = convert_bytes_to_human_readable(video_size)
    scrapy_logger.info('  '.join([aweme.username, aweme.aweme_url, aweme.create_time_str,
                                  os.path.relpath(save_path, '/root/download/douyin/'), human_readable_size]))
    if video_size > MAX_VIDEO_SIZE:
        aweme.post_data.update(
            {'message': "文件太大({})，[请单击我查看]({})".format(human_readable_size, aweme_video.download_url)})
        r = request_webhook('/send_message', aweme.post_data, scrapy_logger)
        return r
    elif video_content:
        aweme.post_data.update({'files': {'media': save_path, 'caption': media_name}})
        r = request_webhook('/photo-or-video', aweme.post_data, scrapy_logger)
        return r
    else:
        aweme.post_data.update({'message': f"获取[抖音视频]({aweme.aweme_info['url']})失败"})
        r = request_webhook('/send_message', aweme.post_data, scrapy_logger)
        return r


def handler_note_douyin(aweme: Aweme):
    aweme_photos = aweme.aweme_photos()
    photos = []
    with ThreadPoolExecutor() as executor:
        # 使用线程池来执行下载任务
        future_to_url = {
            executor.submit(download, photo, aweme.post_data, scrapy_logger) for photo in aweme_photos}
        for future in as_completed(future_to_url):
            try:
                result = future.result()
                if result:
                    photos.append(result)
            except Exception as e:
                scrapy_logger.info("下载出错：" + str(e))
    aweme.post_data.update({'files': photos})
    r = request_webhook('/send-album', aweme.post_data, scrapy_logger)
    return r
