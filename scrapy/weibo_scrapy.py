import traceback
import urllib3
from tools.database import *
from handler.handler_weibo import *

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


def scrapy_latest_via_cn(user: Following, scrapy_log):
    """
        从 https://m.weibo.cn/ 的用户主页通过api获取用户微博
    """

    def one_page_latest(user_id: str, page, since_id=''):
        params = {'containerid': '230413' + user_id + "_-_WEIBO_SECOND_PROFILE_WEIBO"}
        if page > 1 and since_id != '':
            params.update({'page_type': '03', 'since_id': since_id})
        url = 'https://m.weibo.cn/api/container/getIndex?'
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
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
        if info is None:
            continue
        if info['ok'] == -100:
            if 'api/geetest' in info.get('url', ''):
                scrapy_log.info(f'需要验证, ' + info['url'])
            elif 'pass' in info.get('url', ''):
                scrapy_log.info(f'需要登录, ' + info['url'])
            user_input = input("请打开浏览器访问上面的链接进行验证，验证完成后按回车继续爬取，q退出爬取")
            if user_input == 'q':
                break
        mblogs = []
        page_weibo_min_time = datetime(2099, 12, 31, 12, 12, 12)  # 一页中数据最晚发布的微博的时间
        if info['ok'] == 1:
            if info['data']['cards'][0]['card_type'] == 58 and info['data']['cards'][0]['name'] == '暂无微博':
                scrapy_log.info(f'{user.username} 可能没有微博，或微博设置为私密，跳过')
                break
            cards = info['data']['cards']
            page_weibo_min_time = datetime(2099, 12, 31, 12, 12, 12)  # 一页中数据最晚发布的微博的时间
            for card in cards:
                if card['card_type'] == 9:
                    mblogs.append(card.get('mblog'))
                elif card['card_type'] == 11:
                    for card_in_group in card.get('card_group', []):
                        if card_in_group['card_type'] == 9:
                            mblogs.append(card_in_group.get('mblog'))
                else:
                    pass
        if info['ok'] == 0 and info.get('msg') == '请求过于频繁':
            scrapy_log.info(f'{info.get("msg")}')
            time.sleep(60)
        elif info['ok'] == 0 and info.get('msg') == "这里还没有内容":
            break
        elif info['ok'] == -100:
            scrapy_log.info(f'需要验证')
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
            since_id = info['data'].get('cardlistInfo', {}).get('since_id', '')
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


def scrapy_latest_via_playwright(user: Following, scrapy_log):
    """
    使用 Playwright 模拟浏览器下滑获取最新微博
    """
    scrapy_log.info(
        f'开始获取 {user.username} 截至 {str(user.latest_time)} 的微博，她的主页是 https://www.weibo.com/u/{user.userid}')

    # 用于存储最终筛选出的新微博
    new_weibo_list = []

    # 控制标志：用于在回调函数和主循环之间通信
    state = {
        "should_stop": False,  # 是否应该停止下滑
        "page_count": 0,  # 已处理的页数
        "found_count": 0,  # 本次抓取到的新微博数量
        "is_verifying": False  # 是否遇到了验证码
    }

    def on_response(response):
        """网络请求监听回调"""
        # 过滤：只处理 getIndex 接口，且状态码为 200 的请求
        if "containerid=107603" in response.url and response.status == 200 and not state["should_stop"]:
            try:
                data = response.json()

                # 1. 检查是否需要登录/验证 (对应原有逻辑的 ok == -100)
                if data.get('ok') == -100:
                    url = data.get('url', '')
                    if 'geetest' in url or 'pass' in url:
                        scrapy_log.warning(f"检测到验证需求: {url}")
                        state["is_verifying"] = True
                        # 这里不能直接input，因为是在回调线程里，标记后让主线程处理
                    return

                # 2. 检查是否有内容
                if data.get('ok') != 1:
                    # 可能是“暂无微博”或“请求频繁”
                    return

                # 3. 解析微博卡片 (保留原有的解析逻辑)
                cards = data.get('data', {}).get('cards', [])
                mblogs = []
                print(len(cards))
                for card in cards:
                    # card_type 9: 普通微博
                    if card.get('card_type') == 9:
                        mblogs.append(card.get('mblog'))
                    # card_type 11: 聚合微博(Card Group)
                    elif card.get('card_type') == 11:
                        for card_in_group in card.get('card_group', []):
                            if card_in_group.get('card_type') == 9:
                                mblogs.append(card_in_group.get('mblog'))

                # 4. 时间筛选与处理
                batch_new_count = 0
                has_old_weibo = False  # 标记这一批数据里是否出现了旧微博

                for weibo_info in mblogs:
                    # 获取 ID
                    weibo_id = weibo_info.get('idstr') or weibo_info.get('id')

                    # 获取时间 (沿用原有的 standardize_date)
                    if 'edit_at' in weibo_info:
                        raw_time = weibo_info['edit_at']
                    else:
                        raw_time = weibo_info['created_at']
                    # 保存数据 (沿用原有 save_json)
                    save_json(weibo_edit_count(weibo_info), user.username, weibo_id, weibo_info)
                    # 注意：这里调用你外部定义的 standardize_date
                    latest_edit_time = standardize_date(raw_time)
                    weibo_info['weibo_time'] = latest_edit_time

                    # 构造URL
                    weibo_url = f"https://www.weibo.com/{user.userid}/{weibo_id}"
                    weibo_info['weibo_url'] = weibo_url

                    # >>> 核心判断逻辑 <<<
                    if latest_edit_time > user.latest_time:
                        # 这是一个新微博
                        # 排除仅粉丝可见/V+微博 (mblog_vip_type != 1) 沿用旧逻辑
                        if weibo_info.get('mblog_vip_type', 0) != 1:
                            new_weibo_list.append(weibo_info)
                            batch_new_count += 1
                    else:
                        # 这是一个旧微博
                        has_old_weibo = True

                state["page_count"] += 1
                state["found_count"] += batch_new_count
                scrapy_log.info(
                    f"抓取第 {state['page_count']} 批数据: 发现 {batch_new_count} 条新微博")

                # 5. 停止条件判断
                # 如果这一批数据里包含了旧微博，说明我们已经滑到了历史分割线，可以停止了
                # 或者如果没有下一页的 since_id (data['data']['cardlistInfo']['since_id']) 也可以停止
                since_id = data.get('data', {}).get(
                    'cardlistInfo', {}).get('since_id', '')

                if has_old_weibo:
                    scrapy_log.info(">>> 已触及上次爬取的时间点，停止抓取。")
                    state["should_stop"] = True
                elif str(since_id) == '':
                    scrapy_log.info(">>> 已到达底部，无更多数据。")
                    state["should_stop"] = True

            except Exception as e:
                scrapy_log.error(f"解析响应数据出错: {e}")

    # --- Playwright 主执行流程 ---
    with sync_playwright() as p:
        # 启动浏览器 (headless=True 以适应服务器环境)
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']  # 防检测参数
        )

        # 模拟手机环境 (沿用旧逻辑的 User-Agent 策略，这里用 iPhone)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1',
            viewport={'width': 375, 'height': 812}
        )

        page = context.new_page()

        # 挂载监听函数
        page.on("response", on_response)

        # 访问用户移动端主页
        target_url = f"https://m.weibo.cn/u/{user.userid}"
        try:
            page.goto(target_url, timeout=60000)
            page.wait_for_load_state('networkidle')  # 等待页面加载完毕
        except Exception as e:
            scrapy_log.error(f"页面加载超时或失败: {e}")
            browser.close()
            return []

        # 如果需要处理验证码 (简单判断)
        if "login" in page.url:
            scrapy_log.warning("被重定向到登录页，Playwright模式下需要配置Cookie或扫码。")
            # 这里可以选择截图、报错退出，或者尝试加载本地保存的 context storage
            browser.close()
            return []

        # --- 循环下滑 ---
        # 设置最大下滑次数防止死循环 (比如设为 50 次，约 500 条微博)
        max_scrolls = 50
        scroll_wait_time = 2  # 每次下滑等待秒数

        for i in range(max_scrolls):
            if state["should_stop"]:
                break

            if state["is_verifying"]:
                scrapy_log.warning("检测到需要验证，自动停止当前任务。")
                break

            # 执行下滑
            # scrapy_log.debug(f"执行第 {i+1} 次下滑...")
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except:
                break

            # 等待网络请求返回并被 on_response 处理
            # 如果网络慢，这里需要适当增加，或者使用 page.wait_for_response (比较复杂，sleep够用)
            time.sleep(scroll_wait_time)

            # 可选：检测页面底部 "暂无更多" 元素，如果存在则 break
            # page.query_selector(...)

        scrapy_log.info(f"Playwright 抓取结束。共获取 {len(new_weibo_list)} 条新微博。")
        browser.close()

    # 恢复原来的返回格式：返回新微博列表
    return new_weibo_list


def scrapy_latest_via_com(user: Following, scrapy_log):
    """
        从 https://weibo.com/ 的用户主页通过api获取用户微博
    """
    from curl_cffi import requests
    def one_page_latest(user_id: str, page, since_id=''):
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
            since_id = info['data'].get('cardlistInfo', {}).get('since_id', '')
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
    update_db(scraping.userid, scraping.username, latest_weibo['weibo_time'].strftime('%Y-%m-%d %H:%M:%S'))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        valid = sys.argv[1]
    else:
        valid = 1
    all_followings = get_all_following('weibo', valid)
    send_weibo_url = get_send_url('weibo')
    try:
        for following in all_followings:
            f = Following(*following)
            start(f, send_weibo_url)
        weibo_logger.info("本次任务结束\n\n")
    except Exception as e:
        detailed_error_info = traceback.format_exc()
        weibo_logger.info(detailed_error_info)
