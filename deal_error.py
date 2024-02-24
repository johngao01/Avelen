from handler_douyin import *
from handler_weibo import *
from handler_instagram import *
from database import get_send_url

with open('error.txt', 'r') as f:
    lines = f.readlines()
send_url = get_send_url('')
for line in lines:
    if line.startswith("处理"):
        splits = line.split(' ')
        url = splits[1]
        print(url)
        if url in send_url:
            continue
        if 'weibo' in url:
            r = handle_weibo(url)
        elif 'douyin' in url:
            r = handler_douyin(get_aweme_detail(get_url_id(url)[1]))
        else:
            p = get_post_detail(url)
            r = handler_post(Post(p['data']['xdt_api__v1__media__shortcode__web_info']['items'][0]))
        if type(r) is requests.Response:
            if r.status_code == 200:
                store_message_data(r)
                send_url.append(url)
            else:
                print(f'处理{url}失败')
                log_error(url)
        else:
            continue
