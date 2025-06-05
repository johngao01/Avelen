import traceback
import urllib3
from database import *
from handler_weibo import *

urllib3.disable_warnings()


def get_latest_edit_time(weibo_info):
    if 'edit_at' in weibo_info:
        return standardize_date(weibo_info['edit_at'])
    else:
        return standardize_date(weibo_info['created_at'])


def scrapy_like(uid, scrapy_log):
    scrapy_log.info(f'开始获取喜欢的微博，她的主页是 https://www.weibo.com/u/{uid}')
    page = 0
    all_weibo = []
    while True:
        page += 1
        params = {
            'uid': uid,
            'page': str(page),
            'with_total': 'true',
        }
        try:
            response = requests.get('https://weibo.com/ajax/statuses/likelist', params=params, headers=cookie_headers)
            lists = response.json()['data']['list']
        except Exception as e:
            weibo_logger.error(str(e))
            return all_weibo
        for weibo in lists:
            if 'user' in weibo:
                weibo_url = "https://www.weibo.com" + "/" + weibo['user']['idstr'] + "/" + weibo['idstr']
                weibo['weibo_url'] = weibo_url
                save_json(weibo_edit_count(weibo), weibo['user']['screen_name'], weibo['idstr'], weibo)
                weibo['weibo_time'] = get_latest_edit_time(weibo)
                all_weibo.append(weibo)
        if len(all_weibo) > 60:
            break
        if len(lists) == 0:
            break
    scrapy_log.info(f'获取到{len(all_weibo)}个喜欢的微博，获取喜欢的微博完成')
    return all_weibo


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


def scrapy_latest(user: Following, scrapy_log):
    scrapy_log.info(
        f'开始获取 {user.username} 截至 {str(user.latest_time)} 微博，她的主页是 https://www.weibo.com/u/{user.userid}')
    page = 1
    weibo_list = []
    keep = 5
    while keep:
        page_add = 0
        # 此方法获取的信息不能下载v+内容，但不需要cookie
        info = one_page_latest(user_id=user.userid, page=page)
        if info is None:
            continue
        if info['ok']:
            cards = info['data']['cards']
            cards_num = len(cards)
            page_weibo_min_time = datetime(2099, 12, 31, 12, 12, 12)  # 一页中数据最晚发布的微博的时间
            for card in cards:
                if card['card_type'] == 9:
                    weibo_info = card['mblog']
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
                    if latest_edit_time > user.latest_time:
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
            if page_weibo_min_time <= user.latest_time:
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
    return weibo_list


def start(scraping: Following, has_send):
    if scraping.username == 'favorite':
        new_weibo = scrapy_like(scraping.userid, weibo_logger)
    else:
        new_weibo = scrapy_latest(scraping, weibo_logger)
    if len(new_weibo) == 0:
        weibo_logger.info(f'{scraping.username} 没有新微博\n')
        return
    new_weibo = sorted(new_weibo, key=lambda item: item['weibo_time'])
    latest_weibo = max(new_weibo, key=lambda x: x['weibo_time'])
    error = 0
    for weibo in new_weibo:
        if weibo['weibo_url'] in has_send:
            continue
        try:
            if scraping.username == 'favorite':
                r = handle_weibo(weibo['weibo_url'], weibo_data=weibo)
            else:
                r = handle_weibo(weibo['weibo_url'], userid=scraping.userid, username=scraping.username)
        except Exception:
            error += 1
            log_error(weibo['weibo_url'])
            weibo_logger.error(f"处理 {weibo['weibo_url']} 失败")
            weibo_logger.error(traceback.format_exc())
        else:
            if type(r) is requests.Response and r.status_code == 200:
                download_log(r)
                store_message_data(r)
                rate_control(r, weibo_logger)
                continue
            elif type(r) is str and 'skip' in r:
                continue
            else:
                error += 1
                log_error(weibo['weibo_url'])
                weibo_logger.error(f"处理 {weibo['weibo_url']} 失败")
    weibo_logger.info('\n')
    if len(new_weibo) > 0 and error == 0:
        update_db(scraping.userid, scraping.username, latest_weibo['weibo_time'].strftime('%Y-%m-%d %H:%M:%S'))


if __name__ == '__main__':
    all_followings = get_all_following('weibo')
    send_weibo_url = get_send_url('weibo')
    try:
        for following in all_followings:
            f = Following(*following)
            start(f, send_weibo_url)
        weibo_logger.info("本次任务结束\n\n")
    except Exception as e:
        detailed_error_info = traceback.format_exc()
        weibo_logger.info(detailed_error_info)
