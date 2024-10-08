from handler_douyin import *
from handler_weibo import *
from handler_instagram import *
from database import get_send_url

with open('error.txt', 'r') as f:
    lines = f.readlines()
send_url = get_send_url('')
for line in lines:
    splits = line.split(' ')
    url = splits[3]
    print(url)
    if url in send_url:
        print(url, '完成')
        continue
    if 'weibo' in url:
        r = handle_weibo(url)
    elif 'douyin' in url:
        r = handler_douyin(get_aweme_detail(get_url_id(url)[1]))
    else:
        continue
    send_url.append(url)
    if type(r) is requests.Response:
        if r.status_code == 200:
            store_message_data(r)
        else:
            print(f'处理 {url} 失败')
    else:
        print(f'处理 {url} 失败')
        continue
