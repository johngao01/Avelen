from database import get_send_url
from handler_douyin import *
from handler_weibo import *

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
        else:
            r = handler_douyin(get_aweme_detail(get_url_id(url)[1]))
        if type(r) is requests.Response:
            if r.status_code == 200:
                store_message_data(r)
            else:
                log_error(url)
        else:
            continue
