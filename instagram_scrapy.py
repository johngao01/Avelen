import sys

from database import *
from handler_instagram import *


def get_posts(username, after='', before='null', first=12, last='null'):
    variables = {"data": {"count": 12, "include_relationship_info": 'true', "latest_besties_reel_media": 'true',
                          "latest_reel_media": 'true'}, "username": username}
    if after != '':
        variables.update({"after": after, "before": before, "first": first, "last": last})
    response = graphql_request({
        'fb_dtsg': fb_dtsg,
        'fb_api_caller_class': 'RelayModern',
        'fb_api_req_friendly_name': 'PolarisProfilePostsQuery',
        'variables': json.dumps(variables),
        'server_timestamps': 'true',
        'doc_id': '7354141574647290',
    })
    return response.json()


def scrapy_profile_post(profile: Profile):
    end_cursor = ''
    results = []
    has_next_page = True
    instagram_logger.info(
        f'开始获取 {profile.username} 截至 {str(profile.latest_time)} 的instagram，她的主页是 {profile.url}')
    while has_next_page:
        page_data = get_posts(profile.username, after=end_cursor)
        if page_data:
            page_posts = page_data['data']['xdt_api__v1__feed__user_timeline_graphql_connection']['edges']
            page_posts = [Post(post['node']) for post in page_posts]
            page_info = page_data['data']['xdt_api__v1__feed__user_timeline_graphql_connection']['page_info']
            end_cursor = page_info['end_cursor']
            has_next_page = page_info['has_next_page']
            for post in page_posts:
                if post.create_time > profile.latest_time:
                    save_json(post)
                    results.append(post)
                    print(post.url)
                else:
                    if post.is_pined:
                        continue
                    else:
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


def start():
    if len(sys.argv) < 2:
        instagram_logger.info("开始爬取用户数据")
        all_followings = get_all_following('instagram')
        for following in all_followings:
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
            if len(sys.argv) < 2:
                update_db(latest_post.owner_pk, latest_post.owner_username,
                          latest_post.create_time.strftime("%Y-%m-%d %H:%M:%S"))
                sleep(60)
            else:
                print(f"replace into followings values ('{latest_post.owner_pk}','{latest_post.owner_username}',1,"
                      f"'{latest_post.create_time.strftime('%Y-%m-%d %H:%M:%S')}','instagram','2000-02-15 09:32:50');")
    except Exception as e:
        print(e)
