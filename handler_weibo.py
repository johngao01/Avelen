import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import cv2
import requests
from PIL import Image

script_directory = os.path.dirname(os.path.abspath(__file__))
download_save_root_directory = '/root/download'
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/104.0.0.0 Safari/537.36',
    'referer': 'https://weibo.com/',
    'Content-Type': 'application/json'
}
del_file = ['7e80fb31ec58b1ca2fb3548480e1b95e', '4cf24fe8401f7ab2eba2c6cb82dffb0e', '41e5d4e3002de5cea3c8feae189f0736']

MAX_PHOTO_SIZE = 10 * 1024 * 1024
MAX_PHOTO_TOTAL_PIXEL = 10000
MAX_VIDEO_SIZE = 50 * 1024 * 1024
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024

WEB_HOOK_URL = 'http://localhost:5000'


def weibo_edit_count(weibo_info):
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


def save_json(edit_count, userid, idstr, weibo):
    if edit_count == 0:
        json_path = os.path.join(download_save_root_directory, 'json', userid, idstr + '.json')
    else:
        json_path = os.path.join(download_save_root_directory, 'json', userid, idstr + "_" + str(edit_count) + '.json')
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, mode='w', encoding='utf8') as json_write:
        json.dump(weibo, json_write, ensure_ascii=False, indent=4)


def get_duration_from_cv2(filename):
    cap = cv2.VideoCapture(filename)
    if cap.isOpened():
        rate = cap.get(5)
        frame_num = cap.get(7)
        duration = frame_num / rate
        return duration
    return 0


def save_content(save_dir: str, media_name: str, content: bytes) -> str:
    """
    保存内容到本地
    :param save_dir: 保存目录
    :param media_name: 媒体名字
    :param content: 媒体内容
    :return: 文件地址
    """
    save_path = os.path.join(save_dir, media_name)
    with open(save_path, mode='wb') as f:
        f.write(content)
    return save_path


def bytes2md5(r_bytes):
    file_hash = hashlib.md5()
    file_hash.update(r_bytes)
    return file_hash.hexdigest()


def convert_bytes_to_human_readable(num_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f}{unit}"
        num_bytes /= 1024.0


def download_image(weibo_info, photo_url, pic, pic_id, index):
    """
    多线程下载图片微博中的jpg、mov、gif
    :param weibo_info: 微博数据
    :param photo_url: 图片的下载地址
    :param pic: 图片节点
    :param pic_id: 图片的pic_id
    :param index: 图片的序号
    :return:
    """
    photo_video = []
    file_type = photo_url.split('/')[-1].split('?')[0].split('.')[-1]
    media_name = weibo_info['create_time'] + "_" + weibo_info['id'] + "_" + str(index) + "." + file_type
    save_path = os.path.join(weibo_info['save_dir'], media_name)
    if os.path.exists(save_path):
        with open(save_path, mode='rb') as f:
            pic_content = f.read()
    else:
        response = requests.get(photo_url, headers=weibo_info['header'])
        if response.status_code != 200:
            print("禁止访问的内容：" + weibo_info['url'] + "：pic_id：" + pic_id)
            return photo_video
        pic_content = response.content
        save_path = save_content(weibo_info['save_dir'], media_name, pic_content)
    md5value = bytes2md5(pic_content)
    if pic_content:
        size = len(pic_content)
        if md5value in del_file:
            print("和谐的内容：" + weibo_info['url'] + "：pic_id：" + pic_id)
        else:
            file_data = {
                'media': save_path,
                'caption': media_name,
                'size': size
            }
            if file_type == 'jpg':
                img = Image.open(save_path)
                print(index, save_path, str(img.width) + "*" + str(img.height),
                      convert_bytes_to_human_readable(size))
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
                            {'type': 'document', 'send_url': f"{media_name}太大，[请单击我查看]({photo_url})"})
                photo_video.append(file_data)
            else:
                if size < MAX_VIDEO_SIZE:
                    file_data.update({'type': 'video'})
                else:
                    file_data.update({'type': 'document', 'send_url': f"{media_name}太大，[请单击我查看]({photo_url})"})
                photo_video.append(file_data)
            if pic.get('type') == 'livephoto':
                livephoto_url = pic.get('video')
                media_name = weibo_info['create_time'] + "_" + weibo_info['id'] + "_" + str(index) + '.mov'
                save_path = os.path.join(weibo_info['save_dir'], media_name)
                if os.path.exists(save_path):
                    size = os.path.getsize(save_path)
                else:
                    response = requests.get(livephoto_url, headers=weibo_info['header'])
                    livephoto_content = response.content
                    size = len(livephoto_content)
                    save_path = save_content(weibo_info['save_dir'], media_name, livephoto_content)
                duration = get_duration_from_cv2(save_path)
                print(index, save_path, str(duration), convert_bytes_to_human_readable(size))
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
                            {'type': 'document', 'send_url': f"{media_name}太大，[请单击我查看]({livephoto_url})"})
                    photo_video.append(file_data)
                else:
                    os.remove(save_path)
            return photo_video
    else:
        return photo_video


def standardize_date(created_at):
    created_at = created_at.replace("+0800 ", "")
    ts = datetime.strptime(created_at, "%c")
    full_created_at = ts.strftime("%Y%m%d")
    return full_created_at


def weibo_data(weibo_link):
    weibo_header = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/104.0.0.0 Safari/537.36',
        'referer': 'https://weibo.com/'
    }
    weibo_id = weibo_link.split('/')[-1]
    response = requests.get('https://weibo.com/ajax/statuses/show',
                            params={'id': weibo_id},
                            headers=weibo_header)
    data = response.json()
    user_id = data['user']['idstr']
    weibo_id = data['idstr']
    mblogid = data['mblogid']
    save_json(weibo_edit_count(data), user_id, weibo_id, data)
    create_time = standardize_date(data['created_at'])
    if 'message' in data and data['message'] == '暂无权限查看':
        return
    weibo_header['referer'] = f'https://weibo.com/{user_id}/{weibo_id}'
    weibo_info = {
        'data': data,
        'url': weibo_link,
        'id': weibo_id,
        'create_time': create_time,
        'save_dir': os.path.join(download_save_root_directory, 'weibo', data['user']['screen_name'], data['idstr']),
        'header': weibo_header.update({'referer': f'https://weibo.com/{user_id}/{weibo_id}'})
    }
    os.makedirs(weibo_info['save_dir'], exist_ok=True)
    post_data = {
        'username': data['user']['screen_name'],
        'weibo_link': weibo_link,
        'userid': user_id,
        'idstr': weibo_id,
        'mblogid': mblogid,
        'text_raw': data['text_raw'],
    }
    return weibo_info, post_data


def handler_photo_weibo(weibo_info, post_data):
    photo_video = []
    data = weibo_info['data']
    pic_ids = data.get('pic_ids')
    pic_infos = data.get('pic_infos')
    with ThreadPoolExecutor() as executor:
        # 使用线程池来执行下载任务
        future_to_url = {
            executor.submit(download_image, weibo_info, pic_infos[pic_id].get('largest').get('url'),
                            pic_infos[pic_id], pic_id, i): (
                pic_id, i) for i, pic_id in enumerate(pic_ids, start=1)}
        for future in as_completed(future_to_url):
            try:
                result = future.result()
                if result:
                    photo_video.extend(result)
            except Exception as e:
                print("下载出错：", e)
    post_data.update({'files': photo_video})
    if len(post_data) >= 2:
        r = requests.post(WEB_HOOK_URL + '/send-album', data=json.dumps(post_data), headers=headers)
        return r
    else:
        r = requests.post(WEB_HOOK_URL + '/photo-or-video', data=json.dumps({'message': post_data}))
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
    video_content = requests.get(video_url, weibo_info['header']).content
    media_name = weibo_info['create_time'] + "_" + weibo_info['id'] + ".mp4"
    save_path = save_content(weibo_info['save_dir'], media_name, video_content)
    print(1, save_path, convert_bytes_to_human_readable(len(video_content)))
    if len(video_content) > MAX_VIDEO_SIZE:
        post_data.update({'message': "文件太大，[请单击我查看]({})".format(video_url)})
        r = requests.post(WEB_HOOK_URL + '/send_message', data=json.dumps(post_data))
        return r
    elif video_content:
        post_data.update({'files': {'media': save_path, 'caption': media_name}})
        r = requests.post(WEB_HOOK_URL + '/photo-or-video', data=json.dumps(post_data))
        return r
    else:
        post_data.update({'message': f"获取[微博视频]({weibo_info['url']})失败"})
        r = requests.post(WEB_HOOK_URL + '/send_message', data=json.dumps(post_data))
        return r


def handle_weibo(weibo_url):
    weibo_info, post_data = weibo_data(weibo_url)
    if len(weibo_info['data'].get('pic_ids')) > 0 and weibo_info['data'].get('pic_ids') \
            and weibo_info['data'].get('pic_infos'):
        r = handler_photo_weibo(weibo_info, post_data)
        return r
    else:
        data = weibo_info['data']
        page_info = data.get('page_info')
        if page_info:
            video_url = get_video_url(page_info)
            if video_url:
                r = handler_video_weibo(weibo_info, post_data, video_url)
                return r


def test_weibo(weibo_url):
    response = handle_weibo(weibo_url)
    print(response.text)
