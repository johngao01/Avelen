from tools.database import *
from handler.handler_bilibili import *
from tools.scrapy_runner import run_followings, prepare_followings
from tools.pipeline import process_dispatch_result


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
        process_dispatch_result(
            r,
            scrapy_logger,
            url,
            on_success_update=lambda: update_db(
                scraping.user_id,
                scraping.username,
                dynamic.pub_time.strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        # 成功/跳过/失败的日志和副作用都在 process_dispatch_result 统一处理。


if __name__ == '__main__':
    _, all_followings = prepare_followings('bilibili', default_valid=(1,))
    # 创建 API 客户端
    api = BilibiliAPI(all_cookies=cookies_dict)
    send_url = get_send_url('bilibili')
    run_followings(
        all_followings,
        build_following=lambda raw: Following(*raw),
        run_one=main,
        logger=scrapy_logger,
    )
