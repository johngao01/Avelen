import logging
import pickle
import sys
import time
import traceback

import urllib3

from database import *
from handler_weibo import *

urllib3.disable_warnings()
headers = {
    'authority': 'weibo.com',
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7',
    'client-version': 'v2.35.6',
    'referer': 'https://weibo.com/',
    'sec-ch-ua': '"Google Chrome";v="105", "Not)A;Brand";v="8", "Chromium";v="105"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'server-version': 'v2022.09.23.2',
    'traceparent': '00-3d819258ad9faac2e22d7c82b71d0b58-37d1757024402885-00',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/105.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest',
    'x-xsrf-token': 'lq8kI9X3JhvvbhQRIA0-kLZF',
}


def catch_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            traceback.print_exc()
            # 或者，你可以将栈跟踪信息保存到一个字符串中
            detailed_error_info = traceback.format_exc()
            print(detailed_error_info)
            sys.exit(1)

    return wrapper


class Following:
    def __init__(self, userid, username, scrapy_type, latest_time):
        self.userid = userid
        self.username = username
        self.scrapy_type = scrapy_type
        self.latest_time = datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")


def standardize_date(created_at):
    created_at = created_at.replace("+0800 ", "")
    ts = datetime.strptime(created_at, "%c")
    return ts


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
        self.download_log = []

    def _log(self, level, msg, args, **kwargs):
        super()._log(level, msg, args, **kwargs)
        if self.log_time:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            msg = f'{timestamp} - {msg}'
        self.log_history.append(msg)

    def log(self, level, msg, *args, **kwargs):
        self._log(level, msg, args, **kwargs)

    def download_info(self, msg, *args, **kwargs):
        self.download_log.append(msg)
        self.info(msg, *args, **kwargs)


def one_page_latest(user_id: str, page):
    params = {'container_ext': 'profile_uid:' + user_id, 'containerid': '107603' + user_id,
              'page_type': 'searchall', 'page': page}
    url = 'https://m.weibo.cn/api/container/getIndex?'
    try:
        r = requests.get(url, params=params, headers=headers, verify=False)
        r.raise_for_status()
        json_data = r.json()
        return json_data
    except (json.JSONDecodeError, requests.exceptions.RequestException):
        # 如果r.text不是个json数据类型或者请求出现异常，就触发retry
        pass


def scrapy_latest(user: Following, scrapy_log: MyLogger):
    scrapy_log.info(
        f'开始获取 {user.username} 截至 {str(user.latest_time)} 微博，她的主页是 https://www.weibo.com/u/{user.userid}')
    page = 1
    weibo_list = []
    keep = 5
    max_weibo_time = datetime(2000, 12, 31, 12, 12, 12)
    while keep:
        page_add = 0
        # 此方法获取的信息不能下载v+内容，但不需要cookie
        info = one_page_latest(user_id=user.userid, page=page)
        if info['ok']:
            cards = info['data']['cards']
            cards_num = len(cards)
            page_weibo_latest_time = datetime(2099, 12, 31, 12, 12, 12)  # 一页中数据最晚发布的微博的时间
            for card in cards:
                if card['card_type'] == 9:
                    weibo_info = card['mblog']
                    weibo_id = weibo_info['idstr'] if 'idstr' in weibo_info else weibo_info['id']
                    if 'edit_at' in weibo_info:
                        latest_edit_time = standardize_date(weibo_info['edit_at'])
                    else:
                        latest_edit_time = standardize_date(weibo_info['created_at'])
                    weibo_info['weibo_time'] = latest_edit_time
                    weibo_url = "https://www.weibo.com" + "/" + user.userid + "/" + weibo_id
                    if latest_edit_time > max_weibo_time:
                        max_weibo_time = latest_edit_time
                    if latest_edit_time < page_weibo_latest_time:
                        page_weibo_latest_time = latest_edit_time
                    if user.scrapy_type == 1 and latest_edit_time > user.latest_time:
                        page_add += 1
                        weibo_info['weibo_url'] = weibo_url
                        weibo_list.append(weibo_info)
                    elif weibo_info.get('mblog_vip_type', 0) and latest_edit_time > user.latest_time:
                        page_add += 1
                        weibo_info['weibo_url'] = weibo_url
                        weibo_list.append(weibo_info)
                else:
                    cards_num -= 1
            scrapy_info = f'{user.username} 获取第{page}页完成，一共有{cards_num}个微博'
            if cards_num == 0:
                keep -= 1
            if page_add > 0:
                scrapy_info += f"，本页获得{page_add}个新微博,共有{len(weibo_list)}个新微博"
            else:
                scrapy_info += f"，本页没有新微博,共有{len(weibo_list)}个新微博"
            if page_weibo_latest_time <= user.latest_time:
                scrapy_info += f"，获取新微博完成。"
                scrapy_log.info(scrapy_info)
                break
            else:
                scrapy_log.info(scrapy_info)
            page += 1
        if info['ok'] == 0 and info.get('msg') == '请求过于频繁':
            scrapy_log.info(f'{info.get("msg")}')
            time.sleep(60)
        elif info['ok'] == 0 and info.get('msg') == "这里还没有内容":
            keep -= 1
    return weibo_list, max_weibo_time.strftime('%Y-%m-%d %H:%M:%S')


def back_data():
    # 获取当前时间的时间戳（以秒为单位）
    current_timestamp = datetime.now().timestamp()
    # 将时间戳转换为字符串
    timestamp_str = int(current_timestamp)
    os.makedirs('/root/download/backup', exist_ok=True)
    cmd = "cp weibo.sqlite.db " + f'/root/download/backup/{timestamp_str}_weibo.sqlite.db'
    print(cmd)
    os.system(cmd)


@catch_errors
def start(scraping: Following, has_send):
    # with open('scrapy.data', mode='rb') as f1:
    #     new_weibo = pickle.load(f1)
    new_weibo, max_weibo_time = scrapy_latest(scraping, logger)
    if len(new_weibo) == 0:
        logger.info(f'{scraping.username} 没有新微博')
        update_db(scraping.userid, max_weibo_time)
        return
    new_weibo = sorted(new_weibo, key=lambda item: item['weibo_time'])
    with open('scrapy.data', mode='wb') as f1:
        pickle.dump(new_weibo, f1)
    previous_weibo_time = scraping.latest_time.strftime("%Y-%m-%d %H:%M:%S")
    for weibo in new_weibo:
        if weibo['weibo_url'] in has_send:
            continue
        logger.info(weibo['weibo_url'])
        r = handle_weibo(weibo['weibo_url'])
        if type(r) is requests.Response:
            if r.status_code == 200:
                previous_weibo_time = weibo['weibo_time'].strftime('%Y-%m-%d %H:%M:%S')
                store_message_data(r)
            else:
                update_db(scraping.userid, previous_weibo_time)
                with open('error_weibo.txt', mode='a', encoding='utf-8') as f1:
                    f1.write(f"处理 {weibo['weibo_url']} 失败\n")
                    f1.write(f"{r.text}\n\n")
                logger.error(f"处理 {weibo['weibo_url']} 失败")
                sys.exit(1)
        else:
            continue
    update_db(scraping.userid, max_weibo_time)


if __name__ == '__main__':
    back_data()
    logger = MyLogger('scrapy', 'logger', mode='w')
    all_followings = get_all_following()
    send_weibo_url = get_send_weibo()
    for following in all_followings:
        f = Following(*following)
        start(f, send_weibo_url)
    back_data()
