import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
from PIL import Image

from tools.utils import *

with open('cookies/johnjohn01.txt') as cookie_file:
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
    'cookie': 'SUBP=0033WrSXqPxfM72-Ws9jqgMF55529P9D9W51vhsNfUfV2YL.VHulT9DN;WBPSESS=gJ7ElPMf_3q2cdj5JUfmvBCyTLpPuA6sKwpyMFrI2wvAnu3g9Yr-LXk8RZ0EwVzH3ZNo_Vdp2RXzXjs4BBoJzDZC3qLHqRffDSd1XU3RNsAnzJYtEo9D7HKvjaX3HOZw-Y992VC7yPKctxof_ywVOPWptY43SWIw3VEaRwGiDLY=;SUB=_2AkMSoiDDf8NxqwFRmfsVyW7qaYp0zQ3EieKk_tEYJRMxHRl-yT8XqlxZtRB6OSIOKwYh5I1-rxzEimXIcPYLDv47DUz8;XSRF-TOKEN=4_zeJNqfBCsDMNEPpT3GCLnR'
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
    f"logs/scrapy_weibo.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",  # 记录 INFO 及以上（INFO、WARNING、ERROR、CRITICAL）
    encoding="utf-8",
    filter=lambda record: record["extra"].get("name") == "scrapy_weibo"
)
weibo_logger = logger.bind(name="scrapy_weibo")


class Following:
    def __init__(self, userid, username, latest_time):
        self.userid = userid
        self.username = username
        if latest_time is None or latest_time == '':
            self.latest_time = datetime(2000, 12, 12, 12, 12, 12)
        else:
            self.latest_time = datetime.strptime(latest_time, "%Y-%m-%d %H:%M:%S")


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
        response = requests.get(photo_url, headers=weibo_info['header'], stream=True)
        save_content(save_path, response)
        if response.status_code != 200:
            weibo_logger.info("禁止访问的内容：" + photo_url)
            return photo_video
    with open(save_path, mode='rb') as f:
        pic_content = f.read()
    md5value = bytes2md5(pic_content)
    if pic_content:
        size = len(pic_content)
        human_readable_size = convert_bytes_to_human_readable(size)
        if md5value in del_file:
            weibo_logger.info("和谐的内容：" + photo_url)
        else:
            file_data = {
                'media': save_path,
                'caption': media_name,
                'size': size
            }
            if file_type == 'jpg':
                img = Image.open(save_path)
                msg = '\t'.join([str(index), save_path, str(img.width) + "*" + str(img.height), human_readable_size])
                weibo_logger.info(msg)
                if img.width + img.height > MAX_PHOTO_TOTAL_PIXEL:
                    if size < MAX_DOCUMENT_SIZE:
                        file_data.update({'type': 'document'})
                    else:
                        file_data.update(
                            {'type': 'document', 'send_url': f"{media_name}太大，[请单击我查看]({photo_url})"})
                else:
                    if size < MAX_PHOTO_SIZE:
                        file_data.update({'type': 'photo'})
                    elif MAX_PHOTO_SIZE < size < MAX_DOCUMENT_SIZE:
                        file_data.update({'type': 'document'})
                    else:
                        file_data.update(
                            {'type': 'document',
                             'send_url': f"{media_name}太大({human_readable_size})，[请单击我查看]({photo_url})"})
                photo_video.append(file_data)
            else:
                if size < MAX_VIDEO_SIZE:
                    file_data.update({'type': 'video'})
                else:
                    file_data.update({'type': 'document',
                                      'send_url': f"{media_name}太大({human_readable_size})，[请单击我查看]({photo_url})"})
                photo_video.append(file_data)
            if pic.get('type') == 'livephoto':
                livephoto_url = pic.get('video')
                media_name = weibo_info['create_date'] + "_" + weibo_info['id'] + "_" + str(index) + '.mov'
                save_path = os.path.join(weibo_info['save_dir'], media_name)
                if os.path.exists(save_path):
                    size = os.path.getsize(save_path)
                else:
                    response = requests.get(livephoto_url, headers=weibo_info['header'])
                    save_content(save_path, response)
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
                        file_data.update(
                            {'type': 'document',
                             'send_url': f"{media_name}太大({human_readable_size})，[请单击我查看]({livephoto_url})"})
                    photo_video.append(file_data)
                else:
                    os.remove(save_path)
            return photo_video
    else:
        return photo_video


def download_video(weibo_info, video_url, index):
    response = requests.get(video_url, weibo_info['header'], stream=True)
    if index is None:
        media_name = weibo_info['create_date'] + "_" + weibo_info['id'] + ".mp4"
    else:
        media_name = weibo_info['create_date'] + "_" + weibo_info['id'] + f"_{index}.mp4"
    save_path = os.path.join(weibo_info['save_dir'], media_name)
    save_content(save_path, response)
    size = os.path.getsize(save_path)
    human_readable_size = convert_bytes_to_human_readable(size)
    msg = '\t'.join([str(index), save_path, human_readable_size])
    weibo_logger.info(msg)
    return {'media': save_path, 'caption': media_name, 'type': 'video', 'size': size}


def weibo_pic_infos(weibo_dict):
    pic_infos = {}
    for item in weibo_dict['mix_media_info']['items']:
        if item['type'] == 'pic':
            pic_infos[item['id']] = item['data']
    return pic_infos


def parse_weibo_data(weibo_data, username):
    user_id = weibo_data['user']['idstr']
    weibo_id = weibo_data['idstr']
    mblogid = weibo_data['mblogid']
    if username:
        save_dir = os.path.join(download_save_root_directory, 'weibo', username)
    else:
        username = weibo_data['user']['screen_name']
        save_dir = os.path.join(download_save_root_directory, 'weibo', weibo_data['user']['screen_name'])
    # save_json(weibo_edit_count(weibo_data), username, weibo_id, weibo_data)
    create_time = standardize_date(weibo_data['created_at'])
    weibo_url = f'https://www.weibo.com/{user_id}/{weibo_id}'
    weibo_header['referer'] = weibo_url
    weibo_info = {
        'data': weibo_data,
        'url': weibo_url,
        'id': weibo_id,
        'create_date': create_time.strftime("%Y%m%d"),
        'save_dir': save_dir,
        'header': weibo_header.update({'referer': f'https://weibo.com/{user_id}/{weibo_id}'})
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
        return False
    elif 'message' in data and (data['message'] == '访问频次过高，请稍后再试'):
        time.sleep(90)
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


def handle_weibo(weibo_url, weibo_data=None, userid=None, username=None):
    if weibo_data:
        weibo_info, post_data = parse_weibo_data(weibo_data, username)
    else:
        weibo_data = get_weibo_data(weibo_url)
        if weibo_data is False:
            return
        weibo_info, post_data = parse_weibo_data(weibo_data, username)
    weibo_dict = weibo_info['data']
    info = weibo_url + '\t' + post_data['create_time'] + '\t' + post_data['text_raw'].replace('\n', '\t') + '\t'
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
        r = handler_mix_media_weibo(weibo_info, post_data, weibo_dict['mix_media_info'])
        return r
    elif type(weibo_dict.get('pic_ids')) is list and len(weibo_dict.get('pic_ids')) > 0:
        if 'pic_infos' in weibo_dict:
            weibo_logger.info(info + '图片微博')
            r = handler_photo_weibo(weibo_info, weibo_dict['pic_infos'], post_data)
            return r
        else:
            weibo_logger.info(info + '图片微博===\t')
    else:
        data = weibo_dict
        page_info = data.get('page_info')
        if page_info:
            video_url = get_video_url(page_info)
            if video_url:
                weibo_logger.info(info + '视频微博')
                r = handler_video_weibo(weibo_info, post_data, video_url)
                return r
            else:
                weibo_logger.info(info + '文字微博')
                return 'skip'
        else:
            weibo_logger.info(info + '文字微博')
            return 'skip'


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
