import hashlib
import json
import logging
import os
import time
from datetime import datetime

import cv2
import requests

script_directory = os.path.dirname(os.path.abspath(__file__))
download_save_root_directory = '/root/download'
MAX_PHOTO_SIZE = 10 * 1024 * 1024
MAX_PHOTO_TOTAL_PIXEL = 7000
MAX_VIDEO_SIZE = 2000 * 1024 * 1024
MAX_DOCUMENT_SIZE = 2000 * 1024 * 1024

SCRAPY_FAVORITE_LIMIT = 60
WEB_HOOK_URL = 'http://localhost:5000'
count = 0  # 发送了消息数量
times = 0  # 第几次发送
rate = 30  # 每分钟限制发送消息数


class MyLogger(logging.Logger):
    def __init__(self, name, filename, stream=True, mode='a', log_time=True):
        self.log_time = log_time
        super().__init__(name)
        filepath = f'{filename}.log'
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        file_handler = logging.FileHandler(filepath, mode=mode, encoding='utf-8')
        file_handler.setLevel(logging.NOTSET)
        f_format = logging.Formatter("%(asctime)s : %(message)s") if log_time else logging.Formatter("%(message)s")
        file_handler.setFormatter(f_format)
        self.addHandler(file_handler)
        if stream:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO)
            stream_handler.setFormatter(f_format)
            self.addHandler(stream_handler)
        self.log_history = []

    def _log(self, level, msg, args, **kwargs):
        super()._log(level, msg, args, **kwargs)
        if self.log_time:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            msg = f'{timestamp} - {msg}'
        self.log_history.append(msg)

    def log(self, level, msg, *args, **kwargs):
        self._log(level, msg, args, **kwargs)


def convert_bytes_to_human_readable(num_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f}{unit}"
        num_bytes /= 1024.0


def get_duration_from_cv2(filepath):
    """
    获取视频文件文件的持续时间
    :param filepath: 文件地址
    :return: 文件持续时间，错误文件则返回0
    """
    cap = cv2.VideoCapture(filepath)
    if cap.isOpened():
        rate = cap.get(5)
        frame_num = cap.get(7)
        duration = frame_num / rate
        return duration
    return 0


def download_log(response):
    response = response.json()
    messages = response['messages']
    message = messages[-1]
    log = (message['USERNAME'] + " " + message['CREATE_TIME'] + " " + message['DATE_TIME'] +
           " " + message['URL'] + " " + message['TEXT_RAW'].replace('\n', ' '))
    with open('send.log', 'a') as f:
        f.write(log + "\n")


def bytes2md5(r_bytes):
    """
    计算bytes数据的MD5值
    :param r_bytes: 字节行数据，请求下载文件的响应或者打开文件读取到的二进制数据
    :return: MD5值
    """
    file_hash = hashlib.md5()
    file_hash.update(r_bytes)
    return file_hash.hexdigest()


def save_content(save_path, response):
    """
    保存内容到本地
    :param save_path: 文件保存地址
    :param response: 请求下载响应
    :return: 文件地址
    """
    try:
        with open(save_path, mode='wb', buffering=8192) as f:
            for chunk in response.iter_content(chunk_size=8192):  # Adjust the chunk size as needed
                if chunk:
                    f.write(chunk)
        return True
    except OSError as e:
        print(e)
        return False


def request_webhook(method, post_data, logger):
    try:
        r = requests.post(WEB_HOOK_URL + method, data=json.dumps(post_data))
    except requests.exceptions.RequestException as e:
        logger.info(e)
    else:
        return r


def rate_control(r, logger):
    global count, times, rate
    count = count + len(r.json()['messages'])
    if count // 30 > times:
        times += 1
        sleep_time = 60 * (1 + times / 10)
        logger.info(str(count) + f"  sleep {sleep_time} seconds")
        time.sleep(sleep_time)


def log_error(url, text=''):
    with open('error.txt', 'a') as f:
        f.write(f"处理 {url} 失败  {text}\n")
