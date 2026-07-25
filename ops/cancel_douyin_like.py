from platforms.douyin import *
import time

CANCEL_STEP_LIMIT = 50
params = {
    'device_platform': 'webapp',
    'aid': '6383',
    'channel': 'channel_pc_web',
}

headers = favorite_headers.copy()
headers['Referer'] = 'https://www.douyin.com/user/self?from_tab_name=main&showTab=like'
headers['x-secsdk-csrf-token'] = 'DOWNGRADE'


def cancel_like(awemes: list[Aweme]):
    step = 0
    while True:
        split_aweme = awemes[step * CANCEL_STEP_LIMIT:(step + 1) * CANCEL_STEP_LIMIT]
        if not split_aweme:
            return
        data = {
            'aweme_ids': '',
            'item_type_map': {},
        }
        aweme_ids = []
        aweme_dict = {}
        for item in split_aweme:
            aweme_id = item.aweme_id
            aweme_ids.append(aweme_id)
            aweme_dict[aweme_id] = 0
        data['aweme_ids'] = ','.join(aweme_ids)
        data['item_type_map'] = json.dumps(aweme_dict)
        params['X-Bogus'] = scrapy.new_xbogus.get_x_bogus(params, ((86, 138), (238, 238,)), 23)
        response = requests.post('https://www.douyin.com/aweme/v1/web/cancel/item/digg/multi/',
                                 params=params,
                                 headers=headers,
                                 data=data,
                                 timeout=30)
        response.raise_for_status()
        global total
        total += len(split_aweme)
        print(len(split_aweme), total, response.json())
        step += 1


if __name__ == '__main__':
    total = 0
    while True:
        favorite = Following('MS4wLjABAAAApNPXbVmNjfY-gZIuUlYSgvXCkurwPs7OWsIu3TLb2hA',
                             'favorite', None)
        scrapy = DouyinScrapy(favorite)
        scrapy.get_post_from_api()
        print(f'获取到 {len(scrapy.post)} 个喜欢作品')
        cancel_like(scrapy.post)
        print('等待 12 分钟后继续')
        wait_seconds = 60 * 12
        for remaining in range(wait_seconds, 0, -1):
            minutes, seconds = divmod(remaining, 60)
            print(
                f'\r等待下一轮：{minutes:02d}:{seconds:02d}',
                end='',
                flush=True,
            )
            time.sleep(1)
