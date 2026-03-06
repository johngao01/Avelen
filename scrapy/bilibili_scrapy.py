from tools.database import *
import traceback
from handler.handler_bilibili import *


def main(scraping: Following):
    if len(sys.argv) < 2:
        dynamics = api.get_update_dynamics(scraping)
    else:
        dynamics = from_local_json(scraping)
    dynamics = sorted(dynamics, key=lambda x: x.pub_time)
    total = len(dynamics)
    for idx, dynamic in enumerate(dynamics, start=1):
        if dynamic.dynamic_type == 'DYNAMIC_TYPE_AV':
            url = f'https://www.bilibili.com/video/{dynamic.get_video_id()}'
            if url in send_url:
                continue
            post_data = handler_video(dynamic, url, scraping.username, f"{idx}/{total}")
        elif dynamic.dynamic_type == 'DYNAMIC_TYPE_DRAW':
            url = f'https://www.bilibili.com/opus/{dynamic.get_opus_id()}'
            if url in send_url:
                continue
            post_data = handler_opus(dynamic, url, scraping, f"{idx}/{total}", api)
        else:
            continue
        if post_data is None:
            continue
        r = request_webhook('/main', post_data, scrapy_logger)
        if type(r) is requests.Response:
            if r.status_code == 200:
                download_log(r)
                store_message_data(r)
                rate_control(r, scrapy_logger)
                update_db(scraping.user_id, scraping.username, dynamic.pub_time.strftime("%Y-%m-%d %H:%M:%S"))
                continue
            else:
                scrapy_logger.error(f"处理 {url} 失败")
                continue
        else:
            continue


if __name__ == '__main__':
    # 创建 API 客户端
    api = BilibiliAPI(all_cookies=cookies_dict)
    all_followings = get_all_following('bilibili', 1)
    send_url = get_send_url('bilibili')
    try:
        for f in all_followings:
            main(Following(*f))
        scrapy_logger.info("本次任务结束\n\n")
    except Exception as e:
        detailed_error_info = traceback.format_exc()
        scrapy_logger.info(detailed_error_info)
