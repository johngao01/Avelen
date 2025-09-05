from handler import *
from database import get_send_url

# 使用set存储行，避免重复
lines_seen = set()
with open('error.txt', 'r', encoding='utf-8') as file:
    lines = file.readlines()
print(f'一共有{len(lines)}行')

# 过滤重复行
with open('error.txt', 'w', encoding='utf-8') as file:
    for line in lines:
        line = line.strip()  # 去掉行末尾的空白字符
        if line not in lines_seen:
            file.write(line + '\n')
            lines_seen.add(line)
error_line = []
send_url = get_send_url('')
for line in lines_seen:
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
    if type(r) is requests.Response and r.status_code == 200:
        store_message_data(r)
    elif type(r) is str and 'skip' in r:
        continue
    else:
        print(f'处理 {url} 失败')
        error_line.append(line)
        continue

with open('error.txt', 'w', encoding='utf-8') as file:
    for line in error_line:
        line = line.strip()  # 去掉行末尾的空白字符
        file.write(line + '\n')
