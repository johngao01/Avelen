from handler.handler_douyin import *
from handler.handler_weibo import *
from database import get_send_url

# 使用set存储行，避免重复
with open('../error.txt', 'r', encoding='utf-8') as file:
    lines = file.readlines()
error_line = []
send_url = get_send_url('')
lines_seen = set(lines)
total = len(lines_seen)
url_pattern = re.compile(r'https://www\.(douyin|weibo)+\.com\S+')
for i, line in enumerate(lines_seen, start=1):
    # 正则表达式获取url链接
    urls = url_pattern.search(line)
    url = urls[0]
    if url in send_url:
        print(url, '完成')
        continue
    if 'weibo' in url:
        r = handle_weibo(f"{i}/{total}", url, username='favorite')
    elif 'douyin' in url:
        aweme_detail = get_aweme_detail(get_url_id(url)[1])
        if type(aweme_detail) is str and '抱歉，作品不见了' in aweme_detail:
            print(url, aweme_detail, '完成')
            continue
        r = handler_douyin(aweme_detail)
    else:
        continue
    send_url.append(url)
    if type(r) is requests.Response and r.status_code == 200:
        store_message_data(r)
        rate_control(r, weibo_logger)
    elif type(r) is str and 'skip' in r:
        continue
    else:
        if 'douyin' in url and r is True:
            pass
        else:
            print(f'处理 {url} 失败')
            error_line.append(line)
            continue

with open('../error.txt', 'w', encoding='utf-8') as file:
    for line in error_line:
        line = line.strip()  # 去掉行末尾的空白字符
        file.write(line + '\n')
