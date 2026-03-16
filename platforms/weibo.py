import datetime
import time
import sys
import json
import traceback
from datetime import datetime
from pathlib import Path
import requests
from core.platform import BasePlatform
from core.post import BasePost, MediaItem
from core.utils import *
from core.following import FollowUser
from core.downloader import DownloadTask, download_one, Downloader
from core.database import *
from core.scrapy_runner import run_followings, prepare_followings
from core.settings import is_no_send_mode
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent.parent
COOKIE_DIR = BASE_DIR / 'cookies'
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

with open(COOKIE_DIR / 'johnjohn01.txt') as cookie_file:
    cookies = cookie_file.read()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Referer": "https://weibo.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cookie": cookies,
    "X-Requested-With": "XMLHttpRequest",
}
# 获取点赞的内容
cookie_headers = {
    **headers,
    'referer': 'https://weibo.com/u/page/like/7767780215',
}
# 获取单个微博详细信息
weibo_header = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/104.0.0.0 Safari/537.36',
    'referer': 'https://weibo.com/',
    'cookie': cookies
}
del_file = ['7e80fb31ec58b1ca2fb3548480e1b95e', '4cf24fe8401f7ab2eba2c6cb82dffb0e', '41e5d4e3002de5cea3c8feae189f0736',
            '3671086183ed683ec092b43b83fa461c']
from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
)
logger.add(
    str(LOG_DIR / 'scrapy_weibo.log'),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
    encoding="utf-8",
    filter=lambda record: record["extra"].get("name") == "scrapy_weibo"
)
weibo_logger = logger.bind(name="scrapy_weibo")


class Following(FollowUser):
    """微博关注对象（复用统一 FollowUser）。"""

    def __init__(self, userid, username, latest_time: str):
        user = FollowUser.from_db_row(userid, username, latest_time)
        super().__init__(user.userid, user.username, user.latest_time)


def standardize_date(created_at):
    """
    将微博的创建时间标准格式化
    :param created_at: 微博的创建时间
    :return:
    """
    created_at = created_at.replace("+0800 ", "")
    ts = datetime.strptime(created_at, "%c")
    return ts


def weibo_edit_count(weibo_info):
    """
    获取微博的修改次数
    :param weibo_info: 微博数据
    :return: 微博的修改次数
    """
    if 'edit_count' in weibo_info:
        edit_count = weibo_info['edit_count']
    elif 'edit_config' in weibo_info:
        edited = weibo_info['edit_config'].get('edited')
        if edited is False:
            edit_count = 0
        else:
            edit_count = weibo_info['edit_count']
    else:
        edit_count = 0
    return edit_count


def save_json(edit_count, username, idstr, json_data):
    """
    将微博数据存储在本地保存为json文件
    :param edit_count: 微博的修改次数
    :param username: 微博的用户username
    :param idstr: 微博的id
    :param json_data: 微博的数据
    :return:
    """
    if edit_count == 0:
        json_path = os.path.join(download_save_root_directory, 'weibo', 'json', username, idstr + '.json')
    else:
        json_path = os.path.join(download_save_root_directory, 'weibo', 'json', username,
                                 idstr + "_" + str(edit_count) + '.json')
    if os.path.exists(json_path):
        return
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, mode='w', encoding='utf8') as json_write:
        json.dump(json_data, json_write, ensure_ascii=False, indent=4)


def download_image(weibo_info, pic, index):
    """
    多线程下载图片微博中的jpg、mov、gif
    :param weibo_info: 微博数据
    :param pic: 图片节点
    :param index: 图片的序号
    :return:
    """
    photo_video = []
    pic_id = pic['pic_id']
    largest_url = pic['largest']['url']
    photo_url = f"https://wx4.sinaimg.cn/large/{pic_id}"
    file_type = largest_url.split('/')[-1].split('?')[0].split('.')[-1]
    media_name = weibo_info['create_date'] + "_" + weibo_info['id'] + "_" + str(index) + "." + file_type
    save_path = os.path.join(weibo_info['save_dir'], media_name)
    if os.path.exists(save_path):
        pass
    else:
        task = DownloadTask(url=photo_url, save_path=save_path, headers=weibo_info['header'])
        _, response = download_one(task)
        if response.status_code != 200:
            weibo_logger.info("禁止访问的内容：" + photo_url)
            return photo_video
    with open(save_path, mode='rb') as f:
        pic_content = f.read()
    md5value = bytes2md5(pic_content)
    if pic_content:
        if md5value in del_file:
            weibo_logger.info("和谐的内容：" + photo_url)
            return None
        else:
            file_data = handler_file(save_path, index, weibo_logger)
            if file_data:
                photo_video.append(file_data)
            if pic.get('type') == 'livephoto':
                livephoto_url = pic.get('video')
                media_name = weibo_info['create_date'] + "_" + weibo_info['id'] + "_" + str(index) + '.mov'
                save_path = os.path.join(weibo_info['save_dir'], media_name)
                if os.path.exists(save_path):
                    size = os.path.getsize(save_path)
                else:
                    task = DownloadTask(url=livephoto_url, save_path=save_path, headers=weibo_info['header'])
                    _, response = download_one(task)
                    if response.status_code != 200:
                        return photo_video
                    size = os.path.getsize(save_path)
                duration = get_duration_from_cv2(save_path)
                msg = '\t'.join([str(index), save_path, str(duration), convert_bytes_to_human_readable(size)])
                weibo_logger.info(msg)
                if duration:
                    file_data = {
                        'media': save_path,
                        'caption': media_name,
                        'size': size
                    }
                    if size < MAX_VIDEO_SIZE:
                        file_data.update({'type': 'video'})
                    else:
                        pass
                    photo_video.append(file_data)
                else:
                    os.remove(save_path)
            return photo_video
    else:
        return photo_video


def download_video(weibo_info, video_url, index):
    if index is None:
        media_name = weibo_info['create_date'] + "_" + weibo_info['id'] + ".mp4"
    else:
        media_name = weibo_info['create_date'] + "_" + weibo_info['id'] + f"_{index}.mp4"
    save_path = os.path.join(weibo_info['save_dir'], media_name)
    task = DownloadTask(url=video_url, save_path=save_path, headers=weibo_info['header'])
    _, response = download_one(task)
    if response.status_code != 200:
        return None
    size = os.path.getsize(save_path)
    human_readable_size = convert_bytes_to_human_readable(size)
    msg = '\t'.join([str(index), save_path, human_readable_size])
    weibo_logger.info(msg)
    return {'media': save_path, 'caption': media_name, 'type': 'video', 'size': size}


def parse_weibo_data(weibo_data, username):
    user_id = weibo_data['user']['idstr']
    weibo_id = weibo_data['idstr']
    mblogid = weibo_data['mblogid']
    if username is None:
        username = 'favorite'
    save_dir = os.path.join(download_save_root_directory, 'weibo', username)
    if username == 'favorite':
        username = weibo_data['user']['screen_name']
    # save_json(weibo_edit_count(weibo_data), username, weibo_id, weibo_data)
    create_time = standardize_date(weibo_data['created_at'])
    weibo_url = f'https://www.weibo.com/{user_id}/{weibo_id}'
    request_header = {**weibo_header, 'referer': weibo_url}
    weibo_info = {
        'data': weibo_data,
        'url': weibo_url,
        'id': weibo_id,
        'create_date': create_time.strftime("%Y%m%d"),
        'save_dir': save_dir,
        'header': request_header
    }
    os.makedirs(weibo_info['save_dir'], exist_ok=True)
    post_data = {
        'username': username,
        'nickname': weibo_data['user']['screen_name'],
        'url': weibo_url,
        'userid': user_id,
        'idstr': weibo_id,
        'mblogid': mblogid,
        'create_time': create_time.strftime("%Y-%m-%d %H:%M:%S"),
        'text_raw': weibo_data['text_raw'],
    }
    return weibo_info, post_data


class WeiboPost(BasePost):
    def __init__(self, weibo_data, username=None):
        self.data = weibo_data
        self.storage_username = username or 'favorite'
        self.dispatch_username = weibo_data['user']['screen_name'] if self.storage_username == 'favorite' else self.storage_username
        self.mblogid = weibo_data['mblogid']
        self.create_time = standardize_date(weibo_data['created_at'])
        self.create_date = self.create_time.strftime("%Y%m%d")
        self.request_headers = {
            **weibo_header,
            'referer': f"https://www.weibo.com/{weibo_data['user']['idstr']}/{weibo_data['idstr']}",
        }
        super().__init__(
            platform='weibo',
            post_id=weibo_data['idstr'],
            user_id=weibo_data['user']['idstr'],
            username=self.dispatch_username,
            nickname=weibo_data['user']['screen_name'],
            url=f"https://www.weibo.com/{weibo_data['user']['idstr']}/{weibo_data['idstr']}",
            text_raw=weibo_data.get('text_raw', ''),
            create_time=self.create_time,
        )

    def build_media_items(self) -> list[MediaItem]:
        if self.data.get('mix_media_info', {}).get('items'):
            return self._build_mix_media_items()
        pic_ids = self.data.get('pic_ids') or []
        pic_infos = self.data.get('pic_infos') or {}
        if pic_ids and pic_infos:
            items = []
            for index, pic_id in enumerate(pic_ids, start=1):
                pic = pic_infos.get(pic_id)
                if pic:
                    items.extend(self._build_pic_items(pic, index))
            return items
        video_url = get_video_url(self.data.get('page_info') or {})
        if video_url:
            return [self._build_video_item(video_url, 1)]
        return []

    def to_dispatch_data(self, downloaded_files) -> dict | None:
        files = []
        for result in downloaded_files:
            file_data = result.to_dispatch_file()
            if not file_data:
                continue
            if file_data.get('type') in {'photo', 'document'} and self._is_deleted_media(result.path):
                weibo_logger.info("和谐的内容：" + result.path)
                continue
            files.append(file_data)
        if not files:
            return None
        post_data = self.base_dispatch_data()
        post_data['mblogid'] = self.mblogid
        post_data['files'] = files[0] if len(files) == 1 else files
        return post_data

    def _build_mix_media_items(self) -> list[MediaItem]:
        items = []
        mix_media_items = self.data['mix_media_info']['items']
        pic_index = 1
        video_index = 1
        for item in mix_media_items:
            if item['type'] == 'pic':
                items.extend(self._build_pic_items(item['data'], pic_index))
                pic_index += 1
            elif item['type'] == 'video':
                video_url = get_video_url(item['data'])
                if video_url:
                    items.append(self._build_video_item(video_url, video_index))
                    video_index += 1
        return items

    def _build_pic_items(self, pic, index):
        largest_url = pic['largest']['url']
        file_type = largest_url.split('/')[-1].split('?')[0].split('.')[-1]
        filename = f"{self.create_date}_{self.post_id}_{index}.{file_type}"
        items = [MediaItem(
            url=largest_url,
            media_type='photo',
            filename_hint=os.path.join(self.storage_username, filename),
            headers=self.request_headers,
            referer=self.url,
            ext=file_type,
            index=index,
        )]
        if pic.get('type') == 'livephoto' and pic.get('video'):
            items.append(MediaItem(
                url=pic['video'],
                media_type='video',
                filename_hint=os.path.join(self.storage_username, f"{self.create_date}_{self.post_id}_{index}.mov"),
                headers=self.request_headers,
                referer=self.url,
                ext='mov',
                index=index,
            ))
        return items

    def _build_video_item(self, video_url, index):
        suffix = "" if index is None else f"_{index}"
        return MediaItem(
            url=video_url,
            media_type='video',
            filename_hint=os.path.join(self.storage_username, f"{self.create_date}_{self.post_id}{suffix}.mp4"),
            headers=self.request_headers,
            referer=self.url,
            ext='mp4',
            index=index or 1,
        )

    @staticmethod
    def _is_deleted_media(path: str) -> bool:
        try:
            with open(path, mode='rb') as file_obj:
                return bytes2md5(file_obj.read()) in del_file
        except OSError:
            return False


def get_weibo_data(weibo_link):
    weibo_id = weibo_link.split('/')[-1]
    try:
        response = requests.get('https://weibo.com/ajax/statuses/show',
                                params={'id': weibo_id, 'locale': 'zh-CN'},
                                headers=weibo_header)
        data = response.json()
    except Exception as e:
        weibo_logger.error("获取微博信息失败：" + weibo_link)
        log_error(weibo_link, '获取微博失败')
        return False
    if 'message' in data and (data['message'] == '暂无查看权限' or data['message'] == '该微博不存在'):
        weibo_logger.error(data['message'] + "\t" + weibo_link)
        return True
    elif 'message' in data and (data['message'] == '访问频次过高，请稍后再试'):
        time.sleep(90)
    elif data.get('message') == "该内容请至手机客户端查看":
        print(data['message'])
        return True
    data['weibo_url'] = weibo_link
    return data


def handler_photo_weibo(weibo_info, pic_infos, post_data):
    photo_video = []
    data = weibo_info['data']
    pic_ids = data.get('pic_ids')
    with ThreadPoolExecutor() as executor:
        # 使用线程池来执行下载任务
        future_to_url = {
            executor.submit(download_image, weibo_info, pic_infos[pic_id], i): (
                pic_id, i) for i, pic_id in enumerate(pic_ids, start=1)}
        for future in as_completed(future_to_url):
            try:
                result = future.result()
                if result:
                    photo_video.extend(result)
            except Exception as e:
                weibo_logger.info("下载出错：" + str(e))
    post_data.update({'files': photo_video})
    if len(post_data['files']) == 0:
        return
    r = request_webhook('/main', post_data, weibo_logger)
    return r


def get_video_url(page_info):
    url_keys = [
        "mp4_720p_mp4",
        "stream_url",
        "mp4_hd_url",
        "hevc_mp4_hd",
        "mp4_sd_url",
        "mp4_ld_mp4",
        "h265_mp4_hd",
        "h265_mp4_ld",
        "inch_4_mp4_hd",
        "inch_5_5_mp4_hd",
        "inch_5_mp4_hd",
        "stream_url_hd",
        "stream_url"
    ]
    media_info = page_info.get('media_info')
    if not media_info:
        return None
    for key in url_keys:
        url = media_info.get(key)
        if url:
            return url


def handler_video_weibo(weibo_info, post_data, video_url):
    result = download_video(weibo_info, video_url, 1)
    if result['size'] > MAX_VIDEO_SIZE:
        log_error(weibo_info['url'], f"文件太大，{result['media']}")
    elif result['size']:
        post_data.update({'files': result})
        r = request_webhook('/main', post_data, weibo_logger)
        return r
    else:
        log_error(weibo_info['url'], '下载失败')


def handle_weibo(weibo_index, weibo_url, weibo_data=None, userid=None, username=None):
    if weibo_data:
        post = WeiboPost(weibo_data, username=username)
    else:
        weibo_data = get_weibo_data(weibo_url)
        if weibo_data is False:
            return False
        if weibo_data is True:
            return 'skip'
        if 'user' not in weibo_data:
            json_path = find_file_by_name('/root/download/weibo/json', f'{weibo_url.split('/')[-1]}.json')
            if json_path:
                with open(json_path, encoding='utf-8') as f:
                    weibo_data = json.load(f)
            else:
                return False
        post = WeiboPost(weibo_data, username=username)
    weibo_dict = post.data
    info = weibo_index + '\t' + weibo_url + '\t' + post.create_time.strftime("%Y-%m-%d %H:%M:%S") + \
           '\t' + post.text_raw.replace('\n', '\t') + '\t'
    if weibo_dict['mblog_vip_type'] == 1:
        weibo_logger.info(info + 'V+微博')
        return 'skip'
    if isinstance(weibo_dict.get('retweeted_status'), dict) and isinstance(
            weibo_dict.get('retweeted_status').get('user'), dict):
        weibo_logger.info(info + '转发微博')
        return 'skip'
    if userid:
        # 剔除快转微博
        if weibo_dict['user']['idstr'] != userid:
            weibo_logger.info(info + '转发微博')
            return 'skip'
    if 'mix_media_info' in weibo_dict and weibo_dict['mix_media_info']['items']:
        weibo_logger.info(info + '图片视频微博')
    elif type(weibo_dict.get('pic_ids')) is list and len(weibo_dict.get('pic_ids')) > 0:
        weibo_logger.info(info + '图片微博')
    elif get_video_url(weibo_dict.get('page_info') or {}):
        weibo_logger.info(info + '视频微博')
    else:
        weibo_logger.info(info + '文字微博')
        return 'skip'
    downloader = Downloader(logger=weibo_logger)
    post_data = post.to_dispatch_data(downloader.download_post(post))
    if not post_data:
        return 'skip'
    return request_webhook('/main', post_data, weibo_logger)


def handler_mix_media_weibo(weibo_info, post_data, mix_media_data):
    mix_media_items = mix_media_data['items']
    pic_infos = [item['data'] for item in mix_media_items if item['type'] == 'pic']
    photo_video = []
    if pic_infos:
        with ThreadPoolExecutor() as executor:
            # 使用线程池来执行下载任务
            future_to_url = {
                executor.submit(download_image, weibo_info, pic_infos[i], i + 1): i for i in range(len(pic_infos))}
            for future in as_completed(future_to_url):
                try:
                    result = future.result()
                    if result:
                        photo_video.extend(result)
                except Exception as e:
                    weibo_logger.info("下载出错：" + str(e))
    video_infos = [item['data'] for item in mix_media_items if item['type'] == 'video']
    if video_infos:
        for i, video in enumerate(video_infos, start=1):
            video_url = get_video_url(video)
            if video_url:
                result = download_video(weibo_info, video_url, i)
                photo_video.append(result)
    post_data.update({'files': photo_video})
    r = request_webhook('/main', post_data, weibo_logger)
    return r


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


def scrapy_like(uid, scrapy_log):
    weibo_list = []
    page = 1
    since_id = ''
    while True:
        response = requests.get("https://weibo.com/ajax/statuses/likelist", params={
            'uid': uid,
            'page': page,
            'count': 50,
            'since_id': since_id,
        }, headers=cookie_headers)
        info = response.json()
        if info.get('ok') != 1:
            break
        mblogs = info.get('data', {}).get('list') or []
        if not mblogs:
            break
        for weibo_info in mblogs:
            if 'user' not in weibo_info:
                continue
            weibo_info['weibo_time'] = standardize_date(weibo_info['created_at'])
            weibo_info['weibo_url'] = f"https://www.weibo.com/{weibo_info['user']['idstr']}/{weibo_info['idstr']}"
            weibo_list.append(weibo_info)
        since_id = info.get('data', {}).get('since_id', '')
        scrapy_log.info(f'favorite 获取第{page}页完成，一共有{len(mblogs)}个微博')
        if not since_id:
            break
        page += 1
    return weibo_list


def scrapy_latest_via_com(user: Following, scrapy_log):
    weibo_list = []
    page = 1
    while True:
        params = {"uid": user.userid, "page": page, "feature": 0}
        response = requests.get("https://weibo.com/ajax/statuses/mymblog", params=params, headers=headers)
        info = response.json()
        page_add = 0
        since_id = info.get('data', {}).get('since_id', '')
        if not ('data' in info and 'list' in info['data']):
            return weibo_list
        page_weibo_min_time = datetime(2099, 12, 31, 12, 12, 12)
        if info['ok'] == 0 and info.get('msg') == '请求过于频繁':
            scrapy_log.info(f'{info.get("msg")}')
            time.sleep(60)
        elif info['ok'] == 0 and info.get('msg') == "这里还没有内容":
            break
        elif info['ok'] == -100:
            scrapy_log.info('需要验证')
        mblogs = info['data']['list']
        for weibo_info in mblogs:
            weibo_id = weibo_info['idstr'] if 'idstr' in weibo_info else weibo_info['id']
            if 'edit_at' in weibo_info:
                latest_edit_time = standardize_date(weibo_info['edit_at'])
            else:
                latest_edit_time = standardize_date(weibo_info['created_at'])
            save_json(weibo_edit_count(weibo_info), user.username, weibo_id, weibo_info)
            weibo_info['weibo_time'] = latest_edit_time
            weibo_url = "https://www.weibo.com" + "/" + user.userid + "/" + weibo_id
            if latest_edit_time < page_weibo_min_time:
                page_weibo_min_time = latest_edit_time
            if latest_edit_time > user.latest_time and weibo_info.get('mblog_vip_type', 0) != 1:
                page_add += 1
                weibo_info['weibo_url'] = weibo_url
                weibo_list.append(weibo_info)
        scrapy_info = f'{user.username} 获取第{page}页完成，一共有{len(mblogs)}个微博'
        if page_add > 0:
            scrapy_info += f"，本页获得{page_add}个新微博,共有{len(weibo_list)}个新微博"
        else:
            scrapy_info += f"，本页没有新微博,共有{len(weibo_list)}个新微博"
        if page_weibo_min_time <= user.latest_time or since_id == '':
            scrapy_info += "，获取新微博完成。"
            scrapy_log.info(scrapy_info)
            break
        scrapy_log.info(scrapy_info)
        page += 1
    return weibo_list


def start(scraping: Following, has_send):
    if scraping.username == 'favorite':
        new_weibo = scrapy_like(scraping.userid, weibo_logger)
    else:
        new_weibo = scrapy_latest_via_com(scraping, weibo_logger)
    if len(new_weibo) == 0:
        weibo_logger.info(f'{scraping.username} 没有新微博\n')
        return
    new_weibo = sorted(new_weibo, key=lambda item: item['weibo_time'])
    latest_weibo = max(new_weibo, key=lambda x: x['weibo_time'])
    logger.info(f"{new_weibo[0]['weibo_time']}  {new_weibo[-1]['weibo_time']}")
    total = len(new_weibo)
    for i, weibo in enumerate(new_weibo, start=1):
        if weibo['weibo_url'] in has_send:
            continue
        try:
            if scraping.username == 'favorite':
                r = handle_weibo(f"{i}/{total}", weibo['weibo_url'], weibo_data=weibo, username=scraping.username)
            else:
                r = handle_weibo(f"{i}/{total}", weibo['weibo_url'], userid=scraping.userid, username=scraping.username)
        except Exception:
            log_error(weibo['weibo_url'])
            weibo_logger.error(f"处理 {weibo['weibo_url']} 失败")
            weibo_logger.error(traceback.format_exc())
        else:
            handle_dispatch_result(r, weibo_logger, weibo['weibo_url'])
    weibo_logger.info('\n')
    update_after_batch(lambda: update_db(
        scraping.userid,
        scraping.username,
        latest_weibo['weibo_time'].strftime('%Y-%m-%d %H:%M:%S')
    ))


def main(argv=None):
    _, all_followings = prepare_followings('weibo', default_valid=(1,), argv=argv)
    send_weibo_url = get_send_url('weibo')
    run_followings(
        all_followings,
        build_following=lambda raw: Following(*raw),
        run_one=lambda following: start(following, send_weibo_url),
        logger=weibo_logger,
    )


class WeiboPlatform(BasePlatform):
    name = 'weibo'

    @classmethod
    def run(cls, argv=None):
        return main(argv)


if __name__ == '__main__':
    main()


