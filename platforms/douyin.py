import json
import os.path
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from re import sub
from typing import Any, Dict, Optional
from hashlib import md5
from random import randint, random, choice
from re import compile
from time import time
from urllib.parse import urlencode, quote
from datetime import datetime
from pathlib import Path

import requests

from core.post import BasePost, MediaItem
from core.utils import *
from core.following import FollowUser
from core.downloader import DownloadTask, Downloader
from core.database import *
from core.scrapy_runner import run_followings, prepare_followings
from core.settings import is_no_send_mode
from gmssl import sm3, func
import sys
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
COOKIE_DIR = BASE_DIR / 'cookies'
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

logger.remove()
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
)
logger.add(
    str(LOG_DIR / 'scrapy_douyin.log'),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
    encoding="utf-8",
    filter=lambda record: record["extra"].get("name") == "scrapy_douyin"
)
scrapy_logger = logger.bind(name="scrapy_douyin")

with open(COOKIE_DIR / '小号.txt', mode='r', encoding='utf8') as cookie_file:
    cookies = cookie_file.read()
douyin_headers = {
    'referer': 'https://www.douyin.com/',
    'cookie': cookies,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.183'
}
with open(COOKIE_DIR / '大号.txt', mode='r', encoding='utf-8') as f:
    cookies1 = f.read()
favorite_headers = {
    'referer': 'https://www.douyin.com/',
    'cookie': cookies1,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.183'
}
VIDEO_INDEX = 0
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


class ABogus:
    __filter = compile(r'%([0-9A-F]{2})')
    __arguments = [0, 1, 14]
    __ua_key = "\u0000\u0001\u000e"
    __end_string = "cus"
    __version = [1, 0, 1, 5]
    __browser = "1536|742|1536|864|0|0|0|0|1536|864|1536|864|1536|742|24|24|MacIntel"
    __reg = [
        1937774191,
        1226093241,
        388252375,
        3666478592,
        2842636476,
        372324522,
        3817729613,
        2969243214,
    ]
    __str = {
        "s0": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",
        "s1": "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s2": "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s3": "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe",
        "s4": "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe",
    }

    def __init__(self,
                 # user_agent: str = USERAGENT,
                 platform: str = None, ):
        self.chunk = []
        self.size = 0
        self.reg = self.__reg[:]
        self.ua_code = [
            76,
            98,
            15,
            131,
            97,
            245,
            224,
            133,
            122,
            199,
            241,
            166,
            79,
            34,
            90,
            191,
            128,
            126,
            122,
            98,
            66,
            11,
            14,
            40,
            49,
            110,
            110,
            173,
            67,
            96,
            138,
            252]
        self.browser = self.generate_browser_info(
            platform) if platform else self.__browser
        self.browser_len = len(self.browser)
        self.browser_code = self.char_code_at(self.browser)

    @classmethod
    def list_1(cls, random_num=None, a=170, b=85, c=45, ) -> list:
        return cls.random_list(
            random_num,
            a,
            b,
            1,
            2,
            5,
            c & a,
        )

    @classmethod
    def list_2(cls, random_num=None, a=170, b=85, ) -> list:
        return cls.random_list(
            random_num,
            a,
            b,
            1,
            0,
            0,
            0,
        )

    @classmethod
    def list_3(cls, random_num=None, a=170, b=85, ) -> list:
        return cls.random_list(
            random_num,
            a,
            b,
            1,
            0,
            5,
            0,
        )

    @staticmethod
    def random_list(
            a: float = None,
            b=170,
            c=85,
            d=0,
            e=0,
            f=0,
            g=0,
    ) -> list:
        r = a or (random() * 10000)
        v = [
            r,
            int(r) & 255,
            int(r) >> 8,
        ]
        s = v[1] & b | d
        v.append(s)
        s = v[1] & c | e
        v.append(s)
        s = v[2] & b | f
        v.append(s)
        s = v[2] & c | g
        v.append(s)
        return v[-4:]

    @staticmethod
    def from_char_code(*args):
        return "".join(chr(code) for code in args)

    @classmethod
    def generate_string_1(
            cls,
            random_num_1=None,
            random_num_2=None,
            random_num_3=None,
    ):
        return cls.from_char_code(*cls.list_1(random_num_1)) + cls.from_char_code(
            *cls.list_2(random_num_2)) + cls.from_char_code(*cls.list_3(random_num_3))

    def generate_string_2(
            self,
            url_params: str,
            method="GET",
            start_time=0,
            end_time=0,
    ) -> str:
        a = self.generate_string_2_list(
            url_params,
            method,
            start_time,
            end_time,
        )
        e = self.end_check_num(a)
        a.extend(self.browser_code)
        a.append(e)
        return self.rc4_encrypt(self.from_char_code(*a), "y")

    def generate_string_2_list(
            self,
            url_params: str,
            method="GET",
            start_time=0,
            end_time=0,
    ) -> list:
        start_time = start_time or int(time() * 1000)
        end_time = end_time or (start_time + randint(4, 8))
        params_array = self.generate_params_code(url_params)
        method_array = self.generate_method_code(method)
        return self.list_4(
            (end_time >> 24) & 255,
            params_array[21],
            self.ua_code[23],
            (end_time >> 16) & 255,
            params_array[22],
            self.ua_code[24],
            (end_time >> 8) & 255,
            (end_time >> 0) & 255,
            (start_time >> 24) & 255,
            (start_time >> 16) & 255,
            (start_time >> 8) & 255,
            (start_time >> 0) & 255,
            method_array[21],
            method_array[22],
            int(end_time / 256 / 256 / 256 / 256) >> 0,
            int(start_time / 256 / 256 / 256 / 256) >> 0,
            self.browser_len,
        )

    @staticmethod
    def reg_to_array(a):
        o = [0] * 32
        for i in range(8):
            c = a[i]
            o[4 * i + 3] = (255 & c)
            c >>= 8
            o[4 * i + 2] = (255 & c)
            c >>= 8
            o[4 * i + 1] = (255 & c)
            c >>= 8
            o[4 * i] = (255 & c)

        return o

    def compress(self, a):
        f = self.generate_f(a)
        i = self.reg[:]
        for o in range(64):
            c = self.de(i[0], 12) + i[4] + self.de(self.pe(o), o)
            c = (c & 0xFFFFFFFF)
            c = self.de(c, 7)
            s = (c ^ self.de(i[0], 12)) & 0xFFFFFFFF

            u = self.he(o, i[0], i[1], i[2])
            u = (u + i[3] + s + f[o + 68]) & 0xFFFFFFFF

            b = self.ve(o, i[4], i[5], i[6])
            b = (b + i[7] + c + f[o]) & 0xFFFFFFFF

            i[3] = i[2]
            i[2] = self.de(i[1], 9)
            i[1] = i[0]
            i[0] = u

            i[7] = i[6]
            i[6] = self.de(i[5], 19)
            i[5] = i[4]
            i[4] = (b ^ self.de(b, 9) ^ self.de(b, 17)) & 0xFFFFFFFF

        for l in range(8):
            self.reg[l] = (self.reg[l] ^ i[l]) & 0xFFFFFFFF

    @classmethod
    def generate_f(cls, e):
        r = [0] * 132

        for t in range(16):
            r[t] = (e[4 * t] << 24) | (e[4 * t + 1] <<
                                       16) | (e[4 * t + 2] << 8) | e[4 * t + 3]
            r[t] &= 0xFFFFFFFF

        for n in range(16, 68):
            a = r[n - 16] ^ r[n - 9] ^ cls.de(r[n - 3], 15)
            a = a ^ cls.de(a, 15) ^ cls.de(a, 23)
            r[n] = (a ^ cls.de(r[n - 13], 7) ^ r[n - 6]) & 0xFFFFFFFF

        for n in range(68, 132):
            r[n] = (r[n - 68] ^ r[n - 64]) & 0xFFFFFFFF

        return r

    @staticmethod
    def pad_array(arr, length=60):
        while len(arr) < length:
            arr.append(0)
        return arr

    def fill(self, length=60):
        size = 8 * self.size
        self.chunk.append(128)
        self.chunk = self.pad_array(self.chunk, length)
        for i in range(4):
            self.chunk.append((size >> 8 * (3 - i)) & 255)

    @staticmethod
    def list_4(
            a: int,
            b: int,
            c: int,
            d: int,
            e: int,
            f: int,
            g: int,
            h: int,
            i: int,
            j: int,
            k: int,
            m: int,
            n: int,
            o: int,
            p: int,
            q: int,
            r: int,
    ) -> list:
        return [
            44,
            a,
            0,
            0,
            0,
            0,
            24,
            b,
            n,
            0,
            c,
            d,
            0,
            0,
            0,
            1,
            0,
            239,
            e,
            o,
            f,
            g,
            0,
            0,
            0,
            0,
            h,
            0,
            0,
            14,
            i,
            j,
            0,
            k,
            m,
            3,
            p,
            1,
            q,
            1,
            r,
            0,
            0,
            0]

    @staticmethod
    def end_check_num(a: list):
        r = 0
        for i in a:
            r ^= i
        return r

    @classmethod
    def decode_string(cls, url_string, ):
        decoded = cls.__filter.sub(cls.replace_func, url_string)
        return decoded

    @staticmethod
    def replace_func(match):
        return chr(int(match.group(1), 16))

    @staticmethod
    def de(e, r):
        r %= 32
        return ((e << r) & 0xFFFFFFFF) | (e >> (32 - r))

    @staticmethod
    def pe(e):
        return 2043430169 if 0 <= e < 16 else 2055708042

    @staticmethod
    def he(e, r, t, n):
        if 0 <= e < 16:
            return (r ^ t ^ n) & 0xFFFFFFFF
        elif 16 <= e < 64:
            return (r & t | r & n | t & n) & 0xFFFFFFFF
        raise ValueError

    @staticmethod
    def ve(e, r, t, n):
        if 0 <= e < 16:
            return (r ^ t ^ n) & 0xFFFFFFFF
        elif 16 <= e < 64:
            return (r & t | ~r & n) & 0xFFFFFFFF
        raise ValueError

    @staticmethod
    def convert_to_char_code(a):
        d = []
        for i in a:
            d.append(ord(i))
        return d

    @staticmethod
    def split_array(arr, chunk_size=64):
        result = []
        for i in range(0, len(arr), chunk_size):
            result.append(arr[i:i + chunk_size])
        return result

    @staticmethod
    def char_code_at(s):
        return [ord(char) for char in s]

    def write(self, e, ):
        self.size = len(e)
        if isinstance(e, str):
            e = self.decode_string(e)
            e = self.char_code_at(e)
        if len(e) <= 64:
            self.chunk = e
        else:
            chunks = self.split_array(e, 64)
            for i in chunks[:-1]:
                self.compress(i)
            self.chunk = chunks[-1]

    def reset(self, ):
        self.chunk = []
        self.size = 0
        self.reg = self.__reg[:]

    def sum(self, e, length=60):
        self.reset()
        self.write(e)
        self.fill(length)
        self.compress(self.chunk)
        return self.reg_to_array(self.reg)

    @classmethod
    def generate_result_unit(cls, n, s):
        r = ""
        for i, j in zip(range(18, -1, -6), (16515072, 258048, 4032, 63)):
            r += cls.__str[s][(n & j) >> i]
        return r

    @classmethod
    def generate_result_end(cls, s, e="s4"):
        r = ""
        b = ord(s[120]) << 16
        r += cls.__str[e][(b & 16515072) >> 18]
        r += cls.__str[e][(b & 258048) >> 12]
        r += "=="
        return r

    @classmethod
    def generate_result(cls, s, e="s4"):
        # r = ""
        # for i in range(len(s)//4):
        #     b = ((ord(s[i * 3]) << 16) | (ord(s[i * 3 + 1]))
        #          << 8) | ord(s[i * 3 + 2])
        #     r += cls.generate_result_unit(b, e)
        # return r

        r = []

        for i in range(0, len(s), 3):
            if i + 2 < len(s):
                n = (
                        (ord(s[i]) << 16)
                        | (ord(s[i + 1]) << 8)
                        | ord(s[i + 2])
                )
            elif i + 1 < len(s):
                n = (ord(s[i]) << 16) | (
                        ord(s[i + 1]) << 8
                )
            else:
                n = ord(s[i]) << 16

            for j, k in zip(range(18, -1, -6),
                            (0xFC0000, 0x03F000, 0x0FC0, 0x3F)):
                if j == 6 and i + 1 >= len(s):
                    break
                if j == 0 and i + 2 >= len(s):
                    break
                r.append(cls.__str[e][(n & k) >> j])

        r.append("=" * ((4 - len(r) % 4) % 4))
        return "".join(r)

    @classmethod
    def generate_args_code(cls):
        a = []
        for j in range(24, -1, -8):
            a.append(cls.__arguments[0] >> j)
        a.append(cls.__arguments[1] / 256)
        a.append(cls.__arguments[1] % 256)
        a.append(cls.__arguments[1] >> 24)
        a.append(cls.__arguments[1] >> 16)
        for j in range(24, -1, -8):
            a.append(cls.__arguments[2] >> j)
        return [int(i) & 255 for i in a]

    def generate_method_code(self, method: str = "GET") -> list[int]:
        return self.sm3_to_array(self.sm3_to_array(method + self.__end_string))
        # return self.sum(self.sum(method + self.__end_string))

    def generate_params_code(self, params: str) -> list[int]:
        return self.sm3_to_array(self.sm3_to_array(params + self.__end_string))
        # return self.sum(self.sum(params + self.__end_string))

    @classmethod
    def sm3_to_array(cls, data: str | list) -> list[int]:
        """
        代码参考: https://github.com/Johnserf-Seed/f2/blob/main/f2/utils/abogus.py

        计算请求体的 SM3 哈希值，并将结果转换为整数数组
        Calculate the SM3 hash value of the request body and convert the result to an array of integers

        Args:
            data (Union[str, List[int]]): 输入数据 (Input data).

        Returns:
            List[int]: 哈希值的整数数组 (Array of integers representing the hash value).
        """

        if isinstance(data, str):
            b = data.encode("utf-8")
        else:
            b = bytes(data)  # 将 List[int] 转换为字节数组

        # 将字节数组转换为适合 sm3.sm3_hash 函数处理的列表格式
        h = sm3.sm3_hash(func.bytes_to_list(b))

        # 将十六进制字符串结果转换为十进制整数列表
        return [int(h[i: i + 2], 16) for i in range(0, len(h), 2)]

    @classmethod
    def generate_browser_info(cls, platform: str = "Win32") -> str:
        inner_width = randint(1280, 1920)
        inner_height = randint(720, 1080)
        outer_width = randint(inner_width, 1920)
        outer_height = randint(inner_height, 1080)
        screen_x = 0
        screen_y = choice((0, 30))
        value_list = [
            inner_width,
            inner_height,
            outer_width,
            outer_height,
            screen_x,
            screen_y,
            0,
            0,
            outer_width,
            outer_height,
            outer_width,
            outer_height,
            inner_width,
            inner_height,
            24,
            24,
            platform,
        ]
        return "|".join(str(i) for i in value_list)

    @staticmethod
    def rc4_encrypt(plaintext, key):
        s = list(range(256))
        j = 0

        for i in range(256):
            j = (j + s[i] + ord(key[i % len(key)])) % 256
            s[i], s[j] = s[j], s[i]

        i = 0
        j = 0
        cipher = []

        for k in range(len(plaintext)):
            i = (i + 1) % 256
            j = (j + s[i]) % 256
            s[i], s[j] = s[j], s[i]
            t = (s[i] + s[j]) % 256
            cipher.append(chr(s[t] ^ ord(plaintext[k])))

        return ''.join(cipher)

    def get_value(self,
                  url_params: dict | str,
                  method="GET",
                  start_time=0,
                  end_time=0,
                  random_num_1=None,
                  random_num_2=None,
                  random_num_3=None,
                  ) -> str:
        string_1 = self.generate_string_1(
            random_num_1,
            random_num_2,
            random_num_3,
        )
        string_2 = self.generate_string_2(urlencode(url_params) if isinstance(
            url_params, dict) else url_params, method, start_time, end_time, )
        string = string_1 + string_2
        # return self.generate_result(
        #     string, "s4") + self.generate_result_end(string, "s4")
        return self.generate_result(string, "s4")


class Following(FollowUser):
    """抖音关注对象（复用统一 FollowUser）。"""

    def __init__(self, userid, username, latest_time):
        user = FollowUser.from_db_row(userid, username, latest_time)
        super().__init__(user.userid, user.username, user.latest_time)
        self.user_sec_uid = user.userid


class Aweme(BasePost):
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
            'header': {**favorite_headers, 'referer': self.aweme_url}
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
        super().__init__(
            platform='douyin',
            post_id=self.aweme_id,
            user_id=self.post_data['userid'],
            username=self.post_data['username'],
            nickname=self.post_data['nickname'],
            url=self.aweme_url,
            text_raw=self.describe,
            create_time=self.create_time,
        )

    def save_json(self):
        """
        将抖音数据存储在本地保存为json文件
        :return:
        """
        json_path = os.path.join(download_save_root_directory, 'douyin', 'json', self.username, self.aweme_id + '.json')
        if os.path.exists(json_path):
            return
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
            medias.append(AwemeMedia(self, i, image, 'image'))
            if 'video' in image:
                medias.append(AwemeMedia(self, i, image['video'], 'video'))
        return medias

    def build_media_items(self) -> list[MediaItem]:
        items = []
        headers = {**favorite_headers, 'referer': self.aweme_url}
        if self.is_video:
            media = self.aweme_video()
            items.append(MediaItem(
                url=media.download_url,
                media_type='video',
                filename_hint=media.relative_path(),
                headers=headers,
                referer=self.aweme_url,
                ext='mp4',
                index=1,
            ))
            return items
        for media in self.aweme_photos():
            ext = 'mp4' if media.content_type == 'video' else 'jpg'
            items.append(MediaItem(
                url=media.download_url,
                media_type='video' if media.content_type == 'video' else 'photo',
                filename_hint=media.relative_path(),
                headers=headers,
                referer=self.aweme_url,
                ext=ext,
                index=media.content_index,
            ))
        return items

    def to_dispatch_data(self, downloaded_files) -> dict | None:
        files = [result.to_dispatch_file() for result in downloaded_files if result.to_dispatch_file()]
        if not files:
            return None
        post_data = self.base_dispatch_data()
        post_data['files'] = files[0] if len(files) == 1 else files
        return post_data


class AwemeMedia:
    def __init__(self, media_aweme: Aweme, content_index, node: Optional[Dict[str, Any]] = None, content_type=None):
        self._aweme = media_aweme
        self._node = node
        self.aweme_id = self._aweme.aweme_id
        self.content_index = content_index
        self.username = self._aweme.username
        self.user_sec_uid = self._aweme.user_sec_uid
        self.aweme_url = self._aweme.aweme_url
        self.download_referer = self._aweme.aweme_url
        if content_type:
            self.content_type = content_type
        else:
            self.content_type = 'video' if self._aweme.is_video else 'image'

    @property
    def content_id(self):
        if self.content_type == 'video':
            return self._node['play_addr']['uri']
        else:
            if 'uri' in self._node:
                return self._node['uri']
            return self._node['label_large']['uri']

    @staticmethod
    def generate_data_object(
            data: dict | list,
    ) -> SimpleNamespace | list[SimpleNamespace]:
        def depth_conversion(element):
            if isinstance(element, dict):
                return SimpleNamespace(
                    **{k: depth_conversion(v) for k, v in element.items()}
                )
            elif isinstance(element, list):
                return [depth_conversion(item) for item in element]
            else:
                return element

        return depth_conversion(data)

    @staticmethod
    def safe_extract(
            data: SimpleNamespace | list[SimpleNamespace],
            attribute_chain: str,
            default: str | int | list | dict | SimpleNamespace = "",
    ):
        attributes = attribute_chain.split(".")
        for attribute in attributes:
            if "[" in attribute:
                parts = attribute.split("[", 1)
                attribute = parts[0]
                index = parts[1].split("]", 1)[0]
                try:
                    index = int(index)
                    data = getattr(data, attribute, None)[index]
                except (IndexError, TypeError, ValueError):
                    return default
            else:
                data = getattr(data, attribute, None)
                if not data:
                    return default
        return data or default

    def __extract_video_download(self, data):
        bit_rate: list[SimpleNamespace] = self.safe_extract(
            data,
            "video.bit_rate",
            [],
        )
        try:
            bit_rate: list[tuple[int, int, int, int, int, list[str]]] = [
                (
                    i.FPS,
                    i.bit_rate,
                    i.play_addr.data_size,
                    i.play_addr.height,
                    i.play_addr.width,
                    i.play_addr.url_list,
                )
                for i in bit_rate
            ]
            bit_rate.sort(
                key=lambda x: (
                    max(
                        x[3],
                        x[4],
                    ),
                    x[0],
                    x[1],
                    x[2],
                ),
            )
            return bit_rate[-1][-1][VIDEO_INDEX] if bit_rate else ""
        except AttributeError:
            url = self.safe_extract(
                bit_rate[0],
                f"play_addr.url_list[{VIDEO_INDEX}]",
            )
            return url

    @property
    def download_url(self):
        if self.content_type == 'video':
            download_addr = self.__extract_video_download(self.generate_data_object(self._aweme._node))
            if download_addr:
                return download_addr
            return f'https://aweme.snssdk.com/aweme/v1/play/?video_id={self.content_id}&radio=1080p&line=0'
        else:
            if 'url_list' in self._node:
                return self._node['url_list'][0]
            return self._node['url_list'][0]

    @property
    def save_name(self):
        if len(self._aweme.describe) > 50:
            desc = sub('[\\\\/:*?"<>|\n]', "", self._aweme.describe[0:50])
        else:
            desc = sub('[\\\\/:*?"<>|\n]', "", self._aweme.describe)
        if self.content_type == 'video':
            if self._aweme.is_video:
                return self._aweme.aweme_id + "_" + desc + ".mp4"
            else:
                return self._aweme.aweme_id + "_" + desc + "_" + str(self.content_index) + ".mp4"
        else:
            return self._aweme.aweme_id + "_" + desc + "_" + str(self.content_index) + ".jpg"

    def save_path(self):
        if self.content_type == 'video':
            filepath = os.path.join(self._aweme.aweme_info['save_dir'], self.username, self.save_name)
        else:
            filepath = os.path.join(self._aweme.aweme_info['save_dir'], 'images', self._aweme.username,
                                    self.save_name)
        return filepath

    def relative_path(self):
        if self.content_type == 'video':
            return os.path.join(self.username, self.save_name)
        return os.path.join('images', self._aweme.username, self.save_name)


def get_url_id(share_info: str):
    if share_info.startswith('https://www.douyin.com'):
        url = re.search(r'https://www.douyin.com/(video|note)/(\d{19})/?', share_info).group(0)
        aweme_id = url.split('/')[-1]
    else:
        link = re.search('https://v.douyin.com/[A-Za-z0-9]+/', share_info)
        if link is None:
            url = re.search(r'https://www.iesdouyin.com/share/(video|note)/(\d{19})?', share_info).group(0)
            url = url.replace(r'https://www.iesdouyin.com/share', r'https://www.douyin.com')
            aweme_id = url.split('/')[-1]
        else:
            link = link.group(0)
            r = requests.get(url=link, headers=favorite_headers, allow_redirects=False)
            url = r.headers.get('Location')
            if url.startswith('https://webcast.amemv.com/douyin/webcast/reflow/'):
                return url, ''
            url = re.search(r'https://www.iesdouyin.com/share/(video|note|slides)/(\d{19})?', url).group(0)
            url = url.replace(r'https://www.iesdouyin.com/share', r'https://www.douyin.com')
            aweme_id = url.split('/')[-1]
    return url, aweme_id


def get_aweme_detail(aweme_id):
    params = {'device_platform': 'webapp', 'aid': '6383', 'channel': 'channel_pc_web', 'pc_client_type': 1,
              'version_code': '190500', 'version_name': '19.5.0', 'cookie_enabled': 'true', 'screen_width': 1920,
              'screen_height': 1080, 'browser_language': 'zh-CN', 'browser_platform': 'Win32',
              'browser_name': 'Firefox', 'browser_version': '124.0', 'browser_online': 'true', 'engine_name': 'Gecko',
              'engine_version': '122.0.0.0', 'os_name': 'Windows', 'os_version': '10', 'cpu_core_num': 12,
              'device_memory': 8, 'platform': 'PC', 'msToken': '', 'aweme_id': aweme_id}
    a_bogus = ab_model_2_endpoint(params)
    api_post_url = f'https://www.douyin.com/aweme/v1/web/aweme/detail/?{urlencode(params)}&a_bogus={a_bogus}'
    headers = favorite_headers.copy()
    headers[
        'User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'
    rs = requests.get(api_post_url, params=params, headers=headers, timeout=5)
    if rs.text == '':
        print('空数据')
        json_path = find_file_by_name('/root/download/douyin/json', f'{aweme_id}.json')
        if json_path:
            with open(json_path, encoding='utf-8') as f:
                return json.load(f)
        return None
    response_json = json.loads(rs.text)
    if response_json['aweme_detail'] is None:
        if 'notice' in response_json['filter_detail']:
            result = response_json['filter_detail']['notice']
        json_path = find_file_by_name('/root/download/douyin/json', f'{aweme_id}.json')
        if json_path:
            with open(json_path, encoding='utf-8') as f:
                return json.load(f)
    aweme = response_json['aweme_detail']
    return aweme


def download_media(aweme_media):
    if aweme_media.download_referer:
        favorite_headers.update({'referer': aweme_media.download_referer})
    try:
        task = DownloadTask(url=aweme_media.download_url, save_path='/tmp/.douyin_probe.tmp', headers=favorite_headers)
        resp = requests.get(task.url, headers=task.headers, stream=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return str(e)
    else:
        if aweme_media.content_type == 'image' and resp.headers['Content-Type'].startswith(aweme_media.content_type):
            return resp
        elif aweme_media.content_type == 'video' and resp.headers['Content-Type'].startswith(aweme_media.content_type):
            return resp
        else:
            return None


def download(media: AwemeMedia, aweme_post_data, logger):
    media_name = media.save_name
    save_path = media.save_path()
    if os.path.exists(save_path):
        media_size = os.path.getsize(save_path)
    else:
        error = 0
        while True:
            try:
                download_response = download_media(media)
                break
            except Exception:
                error += 1
                logger.warning('  '.join([aweme_post_data['url'], media.download_url, '下载失败，重试']))
                if error > 3:
                    return None
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        if isinstance(download_response, requests.Response) and save_content(save_path, download_response):
            media_size = os.path.getsize(save_path)
        else:
            logger.info(
                '  '.join([aweme_post_data['url'], media.content_id, media_name, media.download_url, '下载失败']))
            return None
    human_readable_size = convert_bytes_to_human_readable(media_size)
    if media.content_type == 'video':
        logger.info('  '.join([aweme_post_data['username'], aweme_post_data['url'], aweme_post_data['create_time'],
                               os.path.relpath(save_path, '/root/download/douyin/'), human_readable_size]))
    else:
        logger.info('  '.join(['', os.path.relpath(save_path, '/root/download/douyin/'), human_readable_size]))
    photo_data = {
        'media': save_path,
        'caption': media_name,
        'size': media_size
    }
    if media_size > MAX_VIDEO_SIZE:
        log_error(aweme_post_data['url'], f'文件太大，{save_path} {human_readable_size}')
        return False
    elif media_size:
        photo_data.update({'type': 'video'}) if media.content_type == 'video' else photo_data.update({'type': 'photo'})
        return photo_data
    return False


def dispatch_aweme(aweme: Aweme):
    downloader = Downloader(logger=scrapy_logger)
    post_data = aweme.to_dispatch_data(downloader.download_post(aweme))
    if not post_data:
        log_error(aweme.aweme_url, '获取失败')
        return False
    return request_webhook('/main', post_data, scrapy_logger)


def handler_video_douyin(aweme: Aweme):
    return dispatch_aweme(aweme)


def handler_note_douyin(aweme: Aweme):
    return dispatch_aweme(aweme)


def handler_douyin(aweme):
    if aweme is None:
        return False
    if 'create_time' in aweme:
        aweme['create_time'] = datetime.fromtimestamp(aweme['create_time'])
    else:
        aweme['create_time'] = datetime.strptime(aweme['create_time_str'], "%Y-%m-%d %H:%M:%S")
    user = Following(aweme['author']['sec_uid'], 'favorite', '')
    aweme = Aweme(user, aweme)
    if aweme.is_video:
        r = handler_video_douyin(aweme)
    else:
        r = handler_note_douyin(aweme)
    if getattr(r, 'status_code', None) == 200:
        download_log(r)
        return True
    return False


def ab_model_2_endpoint(params: dict) -> str:
    if not isinstance(params, dict):
        raise TypeError("参数必须是字典类型")
    try:
        ab_value = ABogus().get_value(params)
    except Exception as e:
        raise RuntimeError("生成A-Bogus失败: {0})".format(e))
    return quote(ab_value, safe='')


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


def update_after_batch(on_update=None):
    if not is_no_send_mode() and on_update:
        on_update()


class Scrapy:
    def __init__(self, user: Following):
        self.username = user.username
        self.user_sec_uid = user.user_sec_uid
        self.last_one_time = user.latest_time or datetime(2000, 12, 12, 12, 12, 12)
        self.max_cursor = 0
        self.max_time = datetime(2000, 12, 31, 12, 12, 12)
        self.page = 1
        self.new_xbogus = NewXBogus()
        self.header = {
            'referer': 'https://www.douyin.com/',
            'cookie': cookies,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.183'
        }
        self.awemes = []

    def scrapy_aweme(self):
        scrapy_logger.info(
            f'开始获取 {self.username} 截至 {str(self.last_one_time)} 抖音，她的主页是 {user_url}{self.user_sec_uid}')
        while True:
            params = {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "sec_user_id": self.user_sec_uid,
                "max_cursor": self.max_cursor,
                "count": "18",
                "cookie_enabled": "true",
                "platform": "PC",
                "downlink": "10",
            }
            if self.username == 'favorite':
                params.update({
                    "min_cursor": "0",
                    "whale_cut_token": "",
                    "cut_version": "1",
                    "publish_video_strategy_type": "2",
                    "pc_client_type": "1",
                    "version_code": "170400",
                    "version_name": "17.4.0",
                })
            params['X-Bogus'] = self.new_xbogus.get_x_bogus(params, ((86, 138), (238, 238,)), 23)
            if self.username == 'favorite':
                if self.user_sec_uid.endswith('WeSiDAItgr_J1c'):
                    resp = requests.get(
                        url="https://www.douyin.com/aweme/v1/web/aweme/favorite/",
                        headers=douyin_headers,
                        params=params,
                        timeout=30,
                    )
                else:
                    resp = requests.get(
                        url="https://www.douyin.com/aweme/v1/web/aweme/favorite/",
                        headers=favorite_headers,
                        params=params,
                        timeout=30,
                    )
            else:
                resp = requests.get(
                    url='https://www.douyin.com/aweme/v1/web/aweme/post/',
                    headers=self.header,
                    params=params,
                    timeout=30,
                )
            if resp.text == '':
                scrapy_logger.error('爬取失败，空响应')
                raise RuntimeError('爬取失败，空响应')
            try:
                resp = resp.text.encode('utf-8').decode('utf-8')
                data_json = json.loads(resp)
            except Exception:
                print(resp)
                continue
            page_add = 0
            if 'aweme_list' in data_json and data_json['aweme_list'] is None:
                return
            if 'max_cursor' not in data_json:
                continue
            self.max_cursor = data_json['max_cursor']
            page_awemes = data_json['aweme_list']
            page_latest_time = datetime(2099, 12, 31, 12, 12, 12)
            for aweme in page_awemes:
                aweme_create_time = datetime.fromtimestamp(aweme['create_time'])
                if self.username == 'favorite' or aweme_create_time > self.last_one_time:
                    page_add += 1
                    aweme['username'] = self.username
                    aweme['user_sec_uid'] = self.user_sec_uid
                    aweme['create_time'] = aweme_create_time
                    aweme['create_time_str'] = aweme_create_time.strftime("%Y-%m-%d %H:%M:%S")
                    self.awemes.append(aweme)
                if aweme_create_time > self.max_time:
                    self.max_time = aweme_create_time
                if aweme_create_time < page_latest_time:
                    page_latest_time = aweme_create_time
            scrapy_info = f'{self.username} 获取第{self.page}页完成，一共有{len(page_awemes)}个抖音'
            if page_add > 0:
                scrapy_info += f"，本页获得{page_add}个新抖音,共有{len(self.awemes)}个新抖音"
            else:
                scrapy_info += f"，本页没有新抖音,共有{len(self.awemes)}个新抖音"
            if self.username == 'favorite' and len(self.awemes) >= SCRAPY_FAVORITE_LIMIT:
                scrapy_info += "，获取新喜欢完成。"
                scrapy_logger.info(scrapy_info)
                break
            if self.username != 'favorite' and page_latest_time <= self.last_one_time:
                scrapy_info += "，获取新抖音完成。"
                scrapy_logger.info(scrapy_info)
                break
            scrapy_logger.info(scrapy_info)
            self.page += 1
            if not data_json['has_more']:
                scrapy_info += "，获取新抖音结束。"
                scrapy_logger.info(scrapy_info)
                break


def start(scraping: Following, has_send):
    scraping_worker = Scrapy(scraping)
    scraping_worker.scrapy_aweme()
    if scraping_worker.username != 'favorite':
        new_aweme = sorted(scraping_worker.awemes, key=lambda item: item['create_time'])
    else:
        new_aweme = scraping_worker.awemes
    previous_time = scraping.latest_time.strftime("%Y-%m-%d %H:%M:%S")
    if len(new_aweme) == 0:
        scrapy_logger.info(f"{scraping_worker.username} 没有新作品\n")
    for aweme in new_aweme:
        aweme = Aweme(scraping, aweme)
        if aweme.aweme_url in has_send:
            continue
        aweme.save_json()
        if aweme.is_video:
            if aweme.aweme_info['data']['duration'] > 1800000:
                continue
            r = handler_video_douyin(aweme)
        else:
            r = handler_note_douyin(aweme)
        if handle_dispatch_result(
            r,
            scrapy_logger,
            aweme.aweme_url,
            on_failure_update=lambda: update_db(scraping.user_sec_uid, scraping.username, previous_time)
        ) == 'success':
            previous_time = aweme.create_time_str
    update_after_batch(lambda: update_db(
        scraping.user_sec_uid,
        scraping.username,
        scraping_worker.max_time.strftime("%Y-%m-%d %H:%M:%S")
    ))


def main():
    _, all_followings = prepare_followings('douyin', default_valid=(1,))
    send_url = get_send_url('douyin')
    run_followings(
        all_followings,
        build_following=lambda raw: Following(*raw),
        run_one=lambda following: start(following, send_url),
        logger=scrapy_logger,
    )


if __name__ == '__main__':
    main()


