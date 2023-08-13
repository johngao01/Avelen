import sys

from database import *
from handler_douyin import *


class Scrapy:
    def __init__(self, user: Following):
        self.username = user.username
        self.user_sec_uid = user.user_sec_uid
        self.last_one_time = user.latest_time or datetime(2000, 12, 12, 12, 12, 12)
        self.max_cursor = 0
        self.max_time = datetime(2000, 12, 31, 12, 12, 12)
        self.page = 1
        self.header = {
            'referer': 'https://www.douyin.com/' + self.user_sec_uid,
            'cookie': cookies,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.95 Safari/537.36'
        }
        self.awemes = []

    def scrapy_aweme(self):
        scrapy_logger.info(
            f'开始获取 {self.username} 截至 {str(self.last_one_time)} 抖音，她的主页是 https://www.douyin.com/user/{self.user_sec_uid}')
        while True:
            url = 'https://www.douyin.com/aweme/v1/web/aweme/post/?device_platform=webapp&aid=6383&channel=channel_pc_web&sec_user_id=' + self.user_sec_uid + '&max_cursor=' + str(
                self.max_cursor) + '&locate_query=false&show_live_replay_strategy=1&count=50&publish_video_strategy_type=2&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=1536&screen_height=864&browser_language=zh-CN&browser_platform=Win32&browser_name=Chrome&browser_version=108.0.5359.95&browser_online=true&engine_name=Blink&engine_version=108.0.5359.95&os_name=Windows&os_version=10&cpu_core_num=8&device_memory=8&platform=PC&downlink=10&effective_type=4g&round_trip_time=250'
            resp = requests.get(url, headers=self.header)
            resp = resp.text.encode('utf-8').decode('utf-8')
            data_json = json.loads(resp)
            page_add = 0
            if data_json['aweme_list'] is None:
                return
            self.max_cursor = data_json['max_cursor']
            page_awemes = data_json['aweme_list']
            page_latest_time = datetime(2099, 12, 31, 12, 12, 12)  # 一页中数据最晚发布的抖音的时间
            for aweme in page_awemes:
                aweme_create_time = datetime.fromtimestamp(aweme['create_time'])
                if aweme_create_time > self.last_one_time:
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
            if page_latest_time <= self.last_one_time:
                scrapy_info += f"，获取新抖音完成。"
                scrapy_logger.info(scrapy_info)
                break
            if not data_json['has_more']:
                break


def start(scraping: Following, has_send):
    scrapy = Scrapy(scraping)
    scrapy.scrapy_aweme()
    new_aweme = sorted(scrapy.awemes, key=lambda item: item['create_time'])
    previous_time = scraping.latest_time.strftime("%Y-%m-%d %H:%M:%S")
    for aweme in new_aweme:
        aweme = Aweme(scraping, aweme)
        if aweme.aweme_url in has_send:
            continue
        aweme.save_json()
        if aweme.is_video:
            r = handler_video_douyin(aweme)
        else:
            continue
        if type(r) is requests.Response:
            if r.status_code == 200:
                previous_time = aweme.create_time_str
                store_message_data(r)
            else:
                update_db(scraping.user_sec_uid, previous_time)
                with open('error.txt', mode='a', encoding='utf-8') as f1:
                    f1.write(f"处理 {aweme.aweme_url} 失败\n")
                    f1.write(f"{r.text}\n\n")
                scrapy_logger.error(f"处理 {aweme.aweme_url} 失败")
                os.system('cp sqlite.db sqlite.back')
                sys.exit(1)
        else:
            continue
    update_db(scraping.user_sec_uid, scrapy.max_time.strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == '__main__':
    all_followings = get_all_following('douyin')
    send_url = get_send_url('douyin')
    try:
        for f in all_followings:
            start(Following(*f), send_url)
        scrapy_logger.info("本次任务结束")
    except Exception as e:
        detailed_error_info = traceback.format_exc()
        scrapy_logger.info(detailed_error_info)
    finally:
        os.system('cp sqlite.db sqlite.back')
