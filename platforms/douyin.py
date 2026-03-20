import json
import os.path
import re
import sys
import requests
from re import sub
from typing import Any, Dict
from hashlib import md5
from random import randint, random, choice
from re import compile
from time import time
from urllib.parse import urlencode, quote
from core.platform import BasePlatform
from core.post import BasePost, MediaItem
from core.utils import *
from core.following import FollowUser
from core.database import *
from core.scrapy_runner import (
    dispatch_post,
    handle_dispatch_result,
    prepare_followings,
    run_followings,
    run_posts,
    update_after_batch,
)
from gmssl import sm3, func
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

    def ab_model_2_endpoint(self, params: dict) -> str:
        if not isinstance(params, dict):
            raise TypeError("参数必须是字典类型")
        try:
            ab_value = self.get_value(params)
        except Exception as e:
            raise RuntimeError("生成A-Bogus失败: {0})".format(e))
        return quote(ab_value, safe='')


class Following(FollowUser):
    """抖音关注对象（复用统一 FollowUser）。"""

    def __init__(self, userid, username, latest_time):
        user = FollowUser.from_db_row(userid, username, latest_time)
        super().__init__(user.userid, user.username, user.latest_time)
        self.user_sec_uid = user.userid
        self.url = f'{user_url}{self.user_sec_uid}'
        self.start_msg = f'开始获取 {self.username} 截至 {str(self.latest_time)} 抖音，她的主页是 {self.url}'
        self.end_msg = ''


class Aweme(BasePost):
    """抖音作品对象。

    负责把抖音 aweme 原始节点转换成统一的 BasePost 结构，
    供下载层和发送层复用。
    """

    def __init__(self, following: Following, node: Dict[str, Any]):
        super().__init__()
        self._node = node
        self.username = following.username
        self.user_sec_uid = following.user_sec_uid
        self.aweme_id = node['aweme_id']
        self.id = self.aweme_id
        self.aweme_type = node['aweme_type']
        self.describe = node.get('desc') or ''
        self.duration = node.get('duration', 0)
        self.create_time = datetime.fromtimestamp(node['create_time'])
        self.is_video = self.judge_is_video()

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
    def url(self):
        if self.is_video:
            return video_url + self.aweme_id
        else:
            return note_url + self.aweme_id

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
        if image_infos := self._node.get('image_infos'):
            return image_infos
        if images := self._node.get('images'):
            return images
        image_post_info = self._node.get('image_post_info') or {}
        if isinstance(image_post_info, dict):
            return image_post_info.get('images', [])
        return image_post_info

    def build_media_items(self) -> list[MediaItem]:
        """把抖音作品里的视频/图文节点转换成统一媒体列表。"""
        # 下载请求需要带当前作品页 referer。
        headers = {**favorite_headers, 'referer': self.url}

        # 文件名规则沿用原 AwemeMedia：描述最多 50 个字符，并去掉非法字符。
        desc = self.describe[:50] if len(self.describe) > 50 else self.describe
        desc = sub('[\\\\/:*?"<>|\n]', "", desc)

        def pick_url(url_list):
            if not url_list:
                return ''
            return url_list[VIDEO_INDEX] if len(url_list) > VIDEO_INDEX else url_list[0]

        # 优先从根视频节点里挑最高质量的地址，保持原 AwemeMedia 的排序逻辑。
        def get_best_video_url():
            root_video = self._node.get('video') or {}
            root_bit_rate = root_video.get('bit_rate') or []
            candidates = []
            for item in root_bit_rate:
                if not isinstance(item, dict):
                    continue
                play_addr = item.get('play_addr') or {}
                url_list = play_addr.get('url_list') or []
                if not url_list:
                    continue
                candidates.append((
                    max(play_addr.get('height', 0), play_addr.get('width', 0)),
                    item.get('FPS', 0),
                    item.get('bit_rate', 0),
                    play_addr.get('data_size', 0),
                    url_list,
                ))
            if candidates:
                candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
                return pick_url(candidates[-1][-1])
            if root_bit_rate and isinstance(root_bit_rate[0], dict):
                return pick_url((root_bit_rate[0].get('play_addr') or {}).get('url_list') or [])
            return ''

        # 视频地址优先用最高码率结果；如果没有，就退回 play_addr 或 uri 拼接的兜底地址。
        def resolve_video_url(video):
            if best_video_url:
                return best_video_url
            play_addr = (video or {}).get('play_addr') or {}
            content_id = play_addr.get('uri') or ''
            if content_id:
                return f'https://aweme.snssdk.com/aweme/v1/play/?video_id={content_id}&radio=1080p&line=0'
            return pick_url(play_addr.get('url_list') or [])

        # 统一构造 MediaItem，避免图片和视频分支重复拼字段。
        def make_item(url, media_type, filename_hint, ext, index):
            return MediaItem(
                url=url,
                media_type=media_type,
                filename_hint=filename_hint,
                headers=headers,
                referer=self.url,
                ext=ext,
                index=index,
            )

        best_video_url = get_best_video_url()

        if self.is_video:
            return [make_item(
                url=resolve_video_url(self._node['video']),
                media_type='video',
                filename_hint=os.path.join(self.username, f'{self.aweme_id}_{desc}.mp4'),
                ext='mp4',
                index=1,
            )]

        items = []
        for idx, image in enumerate(self.media_info(), start=1):
            items.append(make_item(
                url=pick_url(image.get('url_list') or []),
                media_type='photo',
                filename_hint=os.path.join('images', self.username, f'{self.aweme_id}_{desc}_{idx}.jpg'),
                ext='jpg',
                index=idx,
            ))
            if 'video' in image:
                items.append(make_item(
                    url=resolve_video_url(image['video']),
                    media_type='video',
                    filename_hint=os.path.join(self.username, f'{self.aweme_id}_{desc}_{idx}.mp4'),
                    ext='mp4',
                    index=idx,
                ))
        return items

    def to_dispatch_data(self, downloaded_files) -> dict | None:
        """把下载结果转换成发送层需要的 payload。"""
        files = [result.to_dispatch_file() for result in downloaded_files if result.to_dispatch_file()]
        if not files:
            return None
        post_data = self.base_dispatch_data()
        if self.username == 'favorite':
            post_data.update({'userid': self._node['author']['sec_uid']})
        post_data['files'] = files[0] if len(files) == 1 else files
        return post_data

    def start(self):
        if self.duration > 1800000:
            return False, self.__str__() + " 视频过长，跳过处理"
        else:
            return True, self.__str__()


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
    a_bogus = ABogus().ab_model_2_endpoint(params)
    api_post_url = f'https://www.douyin.com/aweme/v1/web/aweme/detail/?{urlencode(params)}&a_bogus={a_bogus}'
    headers = favorite_headers.copy()
    headers[
        'User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'
    rs = requests.get(api_post_url, params=params, headers=headers, timeout=5)
    if rs.text == '':
        print('空数据')
        json_path = find_file_by_name('/root/download/douyin/json', f'{aweme_id}.json')
        if json_path:
            with open(json_path, encoding='utf-8') as f1:
                return json.load(f1)
        return None
    response_json = json.loads(rs.text)
    if response_json['aweme_detail'] is None:
        if 'notice' in response_json['filter_detail']:
            result = response_json['filter_detail']['notice']
        json_path = find_file_by_name('/root/download/douyin/json', f'{aweme_id}.json')
        if json_path:
            with open(json_path, encoding='utf-8') as f2:
                return json.load(f2)
    aweme = response_json['aweme_detail']
    return aweme


def handler_douyin(aweme):
    if aweme is None:
        return False
    if isinstance(aweme.get('create_time'), datetime):
        pass
    elif 'create_time' in aweme:
        aweme['create_time'] = datetime.fromtimestamp(aweme['create_time'])
    else:
        aweme['create_time'] = datetime.strptime(aweme['create_time_str'], "%Y-%m-%d %H:%M:%S")
    user = Following(aweme['author']['sec_uid'], 'favorite', '')
    post = Aweme(user, aweme)
    return handle_dispatch_result(dispatch_post(post, scrapy_logger), scrapy_logger, post.url) == 'success'


class DouyinScrapy(BasePlatform):
    """抖音平台抓取器。

    既作为平台注册入口，也作为“单个关注账号”的执行器。
    一个实例只处理一个 following 的内容抓取与过滤。
    """

    name = 'douyin'

    def __init__(self, following: Following):
        self.scraping = following
        self.username = following.username
        self.user_sec_uid = following.user_sec_uid
        self.last_one_time = following.latest_time or datetime(2000, 12, 12, 12, 12, 12)
        self.max_cursor = 0
        self.max_time = self.last_one_time
        self.page = 1
        self.new_xbogus = NewXBogus()
        self.header = {
            'referer': 'https://www.douyin.com/',
            'cookie': cookies,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.183'
        }
        self.post = []

    def get_post_from_api(self):
        """实时请求抖音接口，抓取当前账号的作品列表。"""
        KEEP = True
        while KEEP:
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
            for aweme in data_json['aweme_list']:
                aweme_create_time = datetime.fromtimestamp(aweme['create_time'])
                if self.username == 'favorite' or aweme_create_time > self.last_one_time:
                    page_add += 1
                    aweme['username'] = self.username
                    aweme['user_sec_uid'] = aweme['author']['sec_uid']
                    aweme['create_time_str'] = aweme_create_time.strftime("%Y-%m-%d %H:%M:%S")
                    aweme = Aweme(self.scraping, aweme)
                    aweme.save_json()
                    self.post.append(aweme)
                    if aweme.create_time > self.max_time:
                        self.max_time = aweme.create_time
                    if aweme.create_time < self.scraping.latest_time:
                        KEEP = False
            scrapy_info = f'{self.username} 获取第{self.page}页完成，一共有{len(data_json['aweme_list'])}个抖音'
            if self.username == 'favorite' and len(self.post) >= SCRAPY_FAVORITE_LIMIT:
                scrapy_info += "，获取新喜欢完成。"
                scrapy_logger.info(scrapy_info)
                break
            if self.username != 'favorite' and not KEEP:
                scrapy_info += "，获取新抖音完成。"
                scrapy_logger.info(scrapy_info)
                break
            scrapy_logger.info(scrapy_info)
            self.page += 1
            if not data_json['has_more']:
                scrapy_info += "，获取新抖音结束。"
                scrapy_logger.info(scrapy_info)
                break

    def get_post_from_local(self):
        """从本地 JSON 缓存恢复当前账号的作品列表。"""
        json_dir = os.path.join(download_save_root_directory, 'douyin', 'json', self.username)
        if not os.path.isdir(json_dir):
            scrapy_logger.warning(f'{self.username} 本地 JSON 目录不存在: {json_dir}')
            return

        loaded_post = []
        for filename in os.listdir(json_dir):
            if not filename.endswith('.json'):
                continue
            json_path = os.path.join(json_dir, filename)
            try:
                with open(json_path, encoding='utf-8') as json_file:
                    aweme = json.load(json_file)
            except (OSError, json.JSONDecodeError) as exc:
                scrapy_logger.warning(f'读取本地抖音 JSON 失败: {json_path} {exc}')
                continue

            if aweme.get('create_time_str'):
                aweme_create_time = datetime.strptime(aweme['create_time_str'], "%Y-%m-%d %H:%M:%S")
            else:
                scrapy_logger.warning(f'本地抖音 JSON 缺少时间字段: {json_path}')
                continue

            aweme['username'] = self.username
            aweme['user_sec_uid'] = self.user_sec_uid
            aweme['create_time'] = aweme_create_time
            aweme['create_time_str'] = aweme_create_time.strftime("%Y-%m-%d %H:%M:%S")
            loaded_post.append(Aweme(self.scraping, aweme))

            if aweme_create_time > self.max_time:
                self.max_time = aweme_create_time

        self.post.extend(loaded_post)
        scrapy_logger.info(f'{self.username} 从本地 JSON 获取到 {len(loaded_post)} 个抖音')

    def filter_new_post(self, sent_urls: set[str]):
        """按抖音平台规则过滤出真正要处理的作品。"""
        new_post = []
        for post in self.post:
            if post.aweme_url in sent_urls or post.create_time < self.scraping.latest_time:
                continue
            new_post.append(post)
        if self.scraping.username != 'favorite':
            new_post.sort(key=lambda x: x.create_time)
        return new_post

    def start(self, sent_urls: set[str], use_local_json: bool = False) -> None:
        """执行当前 following 的完整抖音抓取、过滤和发送流程。"""
        if use_local_json:
            self.get_post_from_local()
        else:
            self.get_post_from_api()
        new_post = self.filter_new_post(sent_urls)
        if len(new_post) == 0:
            scrapy_logger.info(f"{self.username} 没有新作品\n")
            self.scraping.end_msg = f'{self.username} 处理结束，没有新作品\n'
            return

        latest_post = new_post[-1]

        scrapy_logger.info(
            f"{self.username} 有 {len(new_post)} 个新作品\n"
        )

        summary = run_posts(
            new_post,
            dispatch_one=lambda post: dispatch_post(post, scrapy_logger),
            logger=scrapy_logger
        )
        update_after_batch(lambda: update_db(
            self.scraping.userid,
            self.scraping.username,
            latest_post.create_time_str,
        ))
        self.scraping.end_msg = (
            f'{self.scraping.username} 处理结束，'
            f'新作品 {summary.total} 个，'
            f'成功 {summary.success} 个，失败 {summary.failure} 个\n'
        )

    @classmethod
    def run(cls, argv=None):
        """抖音平台命令行入口。"""
        return main(argv)


def main(argv=None):
    args, all_followings = prepare_followings(
        'douyin',
        default_valid=(1,),
        argv=argv,
    )
    sent_urls = set(get_send_url('douyin'))
    run_followings(
        all_followings,
        build_following=lambda raw: Following(*raw),
        run_one=lambda following: DouyinScrapy(following).start(sent_urls, use_local_json=args.local_json),
        logger=scrapy_logger,
    )


if __name__ == '__main__':
    main()
