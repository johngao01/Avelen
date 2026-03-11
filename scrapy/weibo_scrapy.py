import traceback
import urllib3
from tools.database import *
from handler.handler_weibo import *
from func_timeout import func_set_timeout
from tools.scrapy_runner import run_followings, build_common_cli_parser, select_followings
from tools.settings import enable_no_send_mode
from tools.pipeline import handle_success, update_after_batch
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
            response = requests.get('https://weibo.com/ajax/statuses/likelist', params=params, headers=headers,
                                    timeout=30)
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


def scrapy_latest_via_com(user: Following, scrapy_log):
    """
        从 https://weibo.com/ 的用户主页通过api获取用户微博
    """
    @func_set_timeout(60)
    def one_page_latest(user_id: str, page, since_id=''):
        from curl_cffi import requests
        params = {'uid': user_id, 'page': page, 'feature': 0}
        if page > 1 and since_id != '':
            params.update({'since_id': since_id})
        url = 'https://weibo.com/ajax/statuses/mymblog?'
        try:
            r = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=20,
                verify=False,  # 必须关闭，否则 H2 会出奇怪问题
                impersonate="chrome120"  # 让它看起来像真浏览器
            )
            # r = requests.get(url, params=params, headers=headers, timeout=30)
            r.raise_for_status()
            json_data = r.json()
            return json_data
        except (json.JSONDecodeError, requests.exceptions.RequestException):
            # 如果r.text不是个json数据类型或者请求出现异常，就触发retry
            pass

    scrapy_log.info(
        f'开始获取 {user.username} 截至 {str(user.latest_time)} 微博，她的主页是 https://www.weibo.com/u/{user.userid}')
    page = 1
    weibo_list = []
    since_id = ''
    while True:
        page_add = 0
        # 此方法获取的信息不能下载v+内容，但不需要cookie
        info = one_page_latest(user_id=user.userid, page=page, since_id=since_id)
        since_id = info.get("data", {}).get("since_id", "")
        if info is None:
            continue
        if info['ok'] == -100:
            if 'api/geetest' in info.get('url', ''):
                scrapy_log.info(f'需要验证, ' + info['url'])
            elif 'pass' in info.get('url', ''):
                scrapy_log.info(f'需要登录, ' + info['url'])
            user_input = input("请打开浏览器访问上面的链接进行验证，验证完成后按回车继续爬取，q退出爬取")
            if user_input == 'q':
                return
        page_weibo_min_time = datetime(2099, 12, 31, 12, 12, 12)  # 一页中数据最晚发布的微博的时间
        if not ('data' in info and 'list' in info['data']):
            return
        if info['ok'] == 0 and info.get('msg') == '请求过于频繁':
            scrapy_log.info(f'{info.get("msg")}')
            time.sleep(60)
        elif info['ok'] == 0 and info.get('msg') == "这里还没有内容":
            break
        elif info['ok'] == -100:
            scrapy_log.info(f'需要验证')
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
            # since_id = info['data'].get('cardlistInfo', {}).get('since_id', '')
        else:
            scrapy_info += f"，本页没有新微博,共有{len(weibo_list)}个新微博"
        if page_weibo_min_time <= user.latest_time or since_id == '':
            scrapy_info += f"，获取新微博完成。"
            scrapy_log.info(scrapy_info)
            break
        else:
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
    error = 0
    total = len(new_weibo)
    for i, weibo in enumerate(new_weibo, start=1):
        if weibo['weibo_url'] in has_send:
            continue
        try:
            if scraping.username == 'favorite':
                r = handle_weibo(
                    f"{i}/{total}", weibo['weibo_url'], weibo_data=weibo, username=scraping.username)
            else:
                r = handle_weibo(
                    f"{i}/{total}", weibo['weibo_url'], userid=scraping.userid, username=scraping.username)
        except Exception:
            error += 1
            log_error(weibo['weibo_url'])
            weibo_logger.error(f"处理 {weibo['weibo_url']} 失败")
            weibo_logger.error(traceback.format_exc())
        else:
            if getattr(r, 'status_code', None) == 200:
                handle_success(r, weibo_logger)
                continue
            elif type(r) is str and 'skip' in r:
                continue
            else:
                error += 1
                log_error(weibo['weibo_url'])
                weibo_logger.error(f"处理 {weibo['weibo_url']} 失败")
    weibo_logger.info('\n')
    update_after_batch(lambda: update_db(
        scraping.userid,
        scraping.username,
        latest_weibo['weibo_time'].strftime('%Y-%m-%d %H:%M:%S')
    ))


if __name__ == '__main__':
    parser = build_common_cli_parser(default_valid=(1,))
    args = parser.parse_args()
    if args.no_send:
        enable_no_send_mode()
    all_followings = select_followings('weibo', args)
    send_weibo_url = get_send_url('weibo')
    run_followings(
        all_followings,
        build_following=lambda raw: Following(*raw),
        run_one=lambda f: start(f, send_weibo_url),
        logger=weibo_logger,
    )
