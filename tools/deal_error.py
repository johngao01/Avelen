from handler import *
from database import get_send_url
from utils import *
# with open('../error.txt', 'r', encoding='utf-8') as file:
#     lines = file.readlines()
#     for line in lines:
#         line = line.strip()  # 去掉行末尾的空白字符
#         if line not in lines_seen:
#             file.write(line + '\n')
#             lines_seen.add(line)
import re
from urllib.parse import urlparse


def find_urls_in_file(file_path):
    """
    从指定文件中查找所有有效的URL，并返回一个去重后的set。

    Args:
        file_path (str): 文件的路径。

    Returns:
        set: 包含所有有效URL的集合。
    """
    urls = set()

    # 这个模式会匹配到空格、引号、逗号等符号之前
    url_pattern = re.compile(r'https://www\.(douyin|weibo)+\.com\S+')

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

            # 1. 使用正则表达式找到所有候选URL
            candidate_urls = url_pattern.findall(content)

            # 2. 使用 urllib.parse 验证每个候选URL
            for url in candidate_urls:
                # urlparse 会将 URL 分解为各个部分
                parsed_url = urlparse(url)

                # 一个有效的URL至少需要有 scheme (协议) 和 netloc (域名)
                if parsed_url.scheme and parsed_url.netloc:
                    urls.add(url)

    except FileNotFoundError:
        print(f"错误: 文件未找到 - {file_path}")
    except Exception as e:
        print(f"处理文件时发生错误: {e}")

    return urls


error_line = []
send_url = get_send_url('')
lines_seen = find_urls_in_file("../logs/scrapy_weibo.log")
total = len(lines_seen)
print(total)
for i, url in enumerate(lines_seen, start=1):
    if url in send_url:
        print(url, '完成')
        continue
    if 'weibo' in url:
        r = handle_weibo(f"{i}/{total}", url)
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
        print(f'处理 {url} 失败')
        error_line.append(url)
        continue
