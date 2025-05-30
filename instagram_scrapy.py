import random

from database import *
from handler_instagram import *


def get_posts(username, after='', before='null', first=12, last='null'):
    variables = {"data": {"count": 12, "include_reel_media_seen_timestamp": True, "include_relationship_info": True,
                 "latest_besties_reel_media": True, "latest_reel_media": True}, "username": username,
        "__relay_internal__pv__PolarisIsLoggedInrelayprovider": True,
        "__relay_internal__pv__PolarisShareSheetV3relayprovider": True}
    if after != '':
        variables.update({"after": after, "before": before, "first": first, "last": last})
    # instagram_headers 会影响爬取失败
    response = graphql_request({
        'fb_dtsg': fb_dtsg,
        'fb_api_caller_class': 'RelayModern',
        'fb_api_req_friendly_name': 'PolarisProfilePostsQuery',
        'variables': json.dumps(variables),
        'server_timestamps': 'true',
        'doc_id': '9830436980396988',
    })
    return response


def scrapy_profile_post(profile: Profile):
    end_cursor = ''
    results = []
    has_next_page = True
    instagram_logger.info(
        f'开始获取 {profile.username} 截至 {str(profile.latest_time)} 的instagram，她的主页是 {profile.url}')
    while has_next_page:
        page_data = get_posts(profile.pk, after=end_cursor)
        if page_data:
            page_posts = page_data['data']['xdt_api__v1__feed__user_timeline_graphql_connection']['edges']
            page_posts_count = len(page_posts)
            page_info = page_data['data']['xdt_api__v1__feed__user_timeline_graphql_connection']['page_info']
            end_cursor = page_info['end_cursor']
            has_next_page = page_info['has_next_page']
            for post in page_posts:
                post = post['node']
                post['nickname'] = profile.username
                post = Post(post)
                if post.create_time > profile.latest_time:
                    page_posts_count -= 1
                    save_json(post)
                    results.append(post)
                    print(post.url)
                else:
                    if post.is_pined:
                        page_posts_count -= 1
            if page_posts_count == 0:
                continue
    instagram_logger.info(f'获取 {profile.username} 完成，获取到{len(results)}个内容')
    return results


def from_local_json():
    for star in os.listdir(root_dir):
        following_posts = []
        star_dir = os.path.join(root_dir, star)
        for file in os.listdir(star_dir):
            path = os.path.join(star_dir, file)
            with open(path, mode='r', encoding='utf8') as json_read:
                item = json.load(json_read)
            following_posts.append(Post(item))
        following_posts = sorted(following_posts, key=lambda x: x.create_time)
        yield following_posts


def random_select_once(elements):
    """
    从列表中随机选择元素，每个元素只选择一次，直到所有元素都选完。
    """
    random.shuffle(elements)  # 随机打乱列表
    for element in elements:
        yield element  # 依次返回元素


def start():
    if len(sys.argv) < 2:
        instagram_logger.info("开始爬取用户数据")
        all_followings = get_all_following('instagram')
        for following in random_select_once(all_followings):
            following = Profile(*following)
            profile_posts = scrapy_profile_post(following)
            yield profile_posts
    else:
        for profile_posts in from_local_json():
            yield profile_posts


if __name__ == '__main__':
    send_url = get_send_url('instagram')
    root_dir = '/root/download/instagram/json/'
    try:
        for posts in start():
            if not posts:
                continue
            latest_post = max(posts, key=lambda x: x.create_time)
            for i, p in enumerate(posts, start=1):
                if p.url in send_url:
                    continue
                instagram_logger.info(' '.join([str(i), p.url, p.create_time.strftime("%Y-%m-%d %H:%M:%S"),
                                                p.text.replace('\n', ''), str(p.media_count)]))
                result = handler_post(p)
                if type(result) is requests.Response:
                    if result.status_code == 200:
                        download_log(result)
                        store_message_data(result)
                        rate_control(result, instagram_logger)
                    else:
                        log_error(p.url, result.status_code)
                else:
                    log_error(p.url, result)
            print(f"replace into user values ('{latest_post.owner_username}','{latest_post.nickname}',"
                  f"'{latest_post.create_time.strftime('%Y-%m-%d %H:%M:%S')}','instagram','{latest_post.create_time.strftime('%Y-%m-%d %H:%M:%S')};")
            update_db(latest_post.owner_username, latest_post.nickname,
                      latest_post.create_time.strftime("%Y-%m-%d %H:%M:%S"))
            print("sleep 60 seconds\n")
            if len(sys.argv) < 2:
                sleep(60)
    except Exception as e:
        print(e)
