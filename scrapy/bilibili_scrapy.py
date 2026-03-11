from tools.database import *
import traceback
import os
from handler.handler_bilibili import *
from tools.scrapy_runner import run_followings, build_common_cli_parser, select_followings


def main(scraping: Following):
    no_send_mode = os.getenv('SCRAPY_NO_SEND', '0') == '1'
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
        if getattr(r, 'status_code', None) == 200:
            if not no_send_mode:
                download_log(r)
                rate_control(r, scrapy_logger)
                update_db(scraping.user_id, scraping.username, dynamic.pub_time.strftime("%Y-%m-%d %H:%M:%S"))
            continue
        else:
            scrapy_logger.error(f"处理 {url} 失败")
            continue


if __name__ == '__main__':
    parser = build_common_cli_parser(default_valid=(1,))
    args = parser.parse_args()
    if args.no_send:
        os.environ['SCRAPY_NO_SEND'] = '1'
    # 创建 API 客户端
    api = BilibiliAPI(all_cookies=cookies_dict)
    all_followings = select_followings('bilibili', args)
    send_url = get_send_url('bilibili')
    run_followings(
        all_followings,
        build_following=lambda raw: Following(*raw),
        run_one=main,
        logger=scrapy_logger,
    )
