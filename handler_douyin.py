import os.path
import time
from re import sub
from typing import Any, Dict, Optional

from utils import *

scrapy_logger = MyLogger('douyin', 'scrapy_douyin', mode='a')

with open('cookies.txt', mode='r', encoding='utf8') as cookie_file:
    cookies = cookie_file.read()
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/104.0.0.0 Safari/537.36',
    'Cookie': cookies
}

video = [0, 4, 51, 55, 58, 61]
images = [2, 68, 150]
video_aweme_detail_url = 'https://www.douyin.com/aweme/v1/web/aweme/detail/?'
domain = 'https://www.douyin.com/'
video_url = 'https://www.douyin.com/video/'
note_url = 'https://www.douyin.com/note/'
user_url = 'https://www.douyin.com/user/'


class XBogus:
    def __init__(self) -> None:

        self.Array = [
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            0, 1, 2, 3, 4, 5, 6, 7, 8, 9, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, None, 10, 11, 12, 13, 14, 15
        ]
        self.character = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="

    def md5_str_to_array(self, md5_str):
        """
        将字符串使用md5哈希算法转换为整数数组。
        Convert a string to an array of integers using the md5 hashing algorithm.
        """
        if isinstance(md5_str, str) and len(md5_str) > 32:
            return [ord(char) for char in md5_str]
        else:
            array = []
            idx = 0
            while idx < len(md5_str):
                array.append((self.Array[ord(md5_str[idx])] << 4) | self.Array[ord(md5_str[idx + 1])])
                idx += 2
            return array

    def md5_encrypt(self, url_path):
        """
        使用多轮md5哈希算法对URL路径进行加密。
        Encrypt the URL path using multiple rounds of md5 hashing.
        """
        hashed_url_path = self.md5_str_to_array(self.md5(self.md5_str_to_array(self.md5(url_path))))
        return hashed_url_path

    def md5(self, input_data):
        """
        计算输入数据的md5哈希值。
        Calculate the md5 hash value of the input data.
        """
        if isinstance(input_data, str):
            array = self.md5_str_to_array(input_data)
        elif isinstance(input_data, list):
            array = input_data
        else:
            raise ValueError("Invalid input type. Expected str or list.")

        md5_hash = hashlib.md5()
        md5_hash.update(bytes(array))
        return md5_hash.hexdigest()

    @staticmethod
    def encoding_conversion(self, a, b, c, e, d, t, f, r, n, o, i, _, x, u, s, l, v, h, p):
        """
        第一次编码转换。
        Perform encoding conversion.
        """
        y = [a, int(i)]
        y.extend([b, _, c, x, e, u, d, s, t, l, f, v, r, h, n, p, o])
        re = bytes(y).decode('ISO-8859-1')
        return re

    @staticmethod
    def encoding_conversion2(self, a, b, c):
        """
        第三次编码转换。
        Perform an encoding conversion on the given input values and return the result.
        """
        return chr(a) + chr(b) + c

    @staticmethod
    def rc4_encrypt(key, data):
        """
        使用RC4算法对数据进行加密。
        Encrypt data using the RC4 algorithm.
        """
        S = list(range(256))
        j = 0
        encrypted_data = bytearray()

        # 初始化 S 盒
        # Initialize the S box
        for i in range(256):
            j = (j + S[i] + key[i % len(key)]) % 256
            S[i], S[j] = S[j], S[i]

        # 生成密文
        # Generate the ciphertext
        i = j = 0
        for byte in data:
            i = (i + 1) % 256
            j = (j + S[i]) % 256
            S[i], S[j] = S[j], S[i]
            encrypted_byte = byte ^ S[(S[i] + S[j]) % 256]
            encrypted_data.append(encrypted_byte)

        return encrypted_data

    def calculation(self, a1, a2, a3):
        """
        对给定的输入值执行位运算计算，并返回结果。
        Perform a calculation using bitwise operations on the given input values and return the result.
        """
        x1 = (a1 & 255) << 16
        x2 = (a2 & 255) << 8
        x3 = x1 | x2 | a3
        return self.character[(x3 & 16515072) >> 18] + self.character[(x3 & 258048) >> 12] + self.character[
            (x3 & 4032) >> 6] + self.character[
            x3 & 63]

    def get_xbogus(self, url_path):
        """
        获取 X-Bogus 值。
        Get the X-Bogus value.
        """
        array1 = self.md5_str_to_array("d88201c9344707acde7261b158656c0e")
        array2 = self.md5_str_to_array(
            self.md5(self.md5_str_to_array("d41d8cd98f00b204e9800998ecf8427e")))
        url_path_array = self.md5_encrypt(url_path)

        timer = int(time.time())
        ct = 536919696
        array3 = []
        array4 = []
        xb_ = ""

        new_array = [
            64, 0.00390625, 1, 8,
            url_path_array[14], url_path_array[15], array2[14], array2[15], array1[14], array1[15],
            timer >> 24 & 255, timer >> 16 & 255, timer >> 8 & 255, timer & 255,
            ct >> 24 & 255, ct >> 16 & 255, ct >> 8 & 255, ct & 255
        ]

        xor_result = new_array[0]
        for i in range(1, len(new_array)):
            # a = xor_result
            b = new_array[i]
            if isinstance(b, float):
                b = int(b)
            xor_result ^= b

        new_array.append(xor_result)

        idx = 0
        while idx < len(new_array):
            array3.append(new_array[idx])
            try:
                array4.append(new_array[idx + 1])
            except IndexError:
                pass
            idx += 2

        merge_array = array3 + array4

        garbled_code = self.encoding_conversion2(
            2, 255, self.rc4_encrypt("ÿ".encode('ISO-8859-1'),
                                     self.encoding_conversion(*merge_array).encode('ISO-8859-1')).decode('ISO-8859-1'))

        idx = 0
        while idx < len(garbled_code):
            xb_ += self.calculation(ord(garbled_code[idx]), ord(
                garbled_code[idx + 1]), ord(garbled_code[idx + 2]))
            idx += 3
        params = '%s&X-Bogus=%s' % (url_path, xb_)
        xb = xb_
        return params, xb


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
            'header': headers.update({'referer': self.aweme_url})
        }
        self.post_data = {
            'username': self.username,
            'url': self.aweme_url,
            'userid': self.user_sec_uid,
            'idstr': self.aweme_id,
            'mblogid': '',
            'create_time': self.create_time_str,
            'text_raw': self.describe,
        }

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
        if self.aweme_type in video:
            return True
        elif self.aweme_type in images:
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
            return self._node.get('image_infos') or self._node.get('images')

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
        headers.update({'referer': referer})
    try:
        resp = requests.get(url, headers=headers, **kwargs)
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


def handler_video_douyin(aweme: Aweme):
    aweme_video = aweme.aweme_video()
    download_response = download_media(aweme_video.download_url, aweme_video.content_type, aweme_video.download_referer,
                                       stream=True)
    if download_response:
        video_content = download_response.content
        media_name = aweme_video.save_name
        save_path = aweme_video.save_path()
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        result = save_content(save_path, video_content)
        scrapy_logger.info('  '.join([aweme.username, aweme.aweme_url, aweme.create_time_str,
                                      os.path.relpath(save_path, '/root/download/douyin/')]))
        if not result:
            aweme.post_data.update({'message': f"获取[抖音视频]({aweme.aweme_info['url']})失败"})
            r = request_webhook('/send_message', aweme.post_data, scrapy_logger)
            return r
        if len(video_content) > MAX_VIDEO_SIZE:
            aweme.post_data.update({'message': "文件太大，[请单击我查看]({})".format(video_url)})
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
