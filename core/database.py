import datetime
import os
import pymysql

mysql_host = os.getenv('MYSQL_HOST', 'rn')
mysql_user = os.getenv('MYSQL_USER', 'root')
mysql_password = os.getenv('MYSQL_PASSWORD', '')
mysql_port = int(os.getenv('MYSQL_PORT', 3306))
mysql_db = os.getenv('MYSQL_DB', 'nicebot')

TGMSG = ['MESSAGE_ID', 'CAPTION', 'DATE_TIME', 'MEDIA_GROUP_ID', 'IDSTR', 'MSG_STR']
POST = ['IDSTR', 'MBLOGID', 'USERID', 'USERNAME', 'URL', 'CREATE_TIME', 'TEXT_RAW']
SORT_FIELD_ALIASES = {
    'scrapy_time': 'scrapy_time',
    'scrapy-time': 'scrapy_time',
    'latest_time': 'latest_time',
    'latest-time': 'latest_time',
    'username': 'username',
    'userid': 'userid',
    'user_id': 'userid',
    'user-id': 'userid',
    'platform': 'platform',
    'valid': 'valid',
}
SORT_DIRECTION_ALIASES = {
    'asc': 'asc',
    'desc': 'desc',
}


def get_db_conn():
    conn = pymysql.connect(host=mysql_host,
                           user=mysql_user,
                           port=mysql_port,
                           password=mysql_password,
                           database=mysql_db,
                           autocommit=True)
    return conn


def insert_data(db_conn, table_name, columns, data_dict):
    cursor = db_conn.cursor()
    columns_str = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    sql = f"REPLACE INTO {table_name} ({columns_str}) VALUES ({placeholders});"
    data = [data_dict[column] for column in columns]
    cursor.execute(sql, data)
    db_conn.commit()


def escape_like_pattern(value: str) -> str:
    """转义 SQL LIKE 通配符，避免部分用户名筛选被 `%` / `_` 干扰。"""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def normalize_sort_option(value: str | None) -> str:
    """把 CLI 排序参数归一化成 `field:direction` 形式。"""
    if value is None or value == '':
        return 'scrapy_time:desc'

    raw_value = value.strip().lower()
    field, separator, direction = raw_value.partition(':')
    normalized_field = SORT_FIELD_ALIASES.get(field)
    if normalized_field is None:
        raise ValueError(
            '排序字段无效，可选 scrapy_time/latest_time/username/userid/platform/valid'
        )

    normalized_direction = 'desc' if not separator else SORT_DIRECTION_ALIASES.get(direction.strip())
    if normalized_direction is None:
        raise ValueError('排序方向无效，只支持 asc 或 desc')

    return f'{normalized_field}:{normalized_direction}'


def parse_sort_option(value: str | None) -> tuple[str, str]:
    """解析排序参数，返回安全白名单字段和 SQL 方向。"""
    normalized = normalize_sort_option(value)
    field, direction = normalized.split(':', 1)
    return field, direction.upper()


def build_filtered_followings_query(columns, platform=None, valid_list=None, user_ids=None, usernames=None,
                                    username_like=None,
                                    latest_time_start=None, latest_time_end=None,
                                    scrapy_time_start=None, scrapy_time_end=None,
                                    sort_option=None):
    """构建统一的 user 表筛选 SQL。

    这个函数只负责：
    - 复用所有 CLI 筛选条件
    - 支持平台可选，便于跨平台查询
    - 通过白名单排序字段生成安全的 ORDER BY
    """
    select_columns = ', '.join(columns)
    sql = [f"SELECT {select_columns} FROM `user` WHERE 1=1"]
    params = []
    sort_field, sort_direction = parse_sort_option(sort_option)

    if platform is not None:
        sql.append("AND platform=%s")
        params.append(platform)

    if valid_list is None:
        valid_list = [1, 2]
    if user_ids is None:
        user_ids = []
    if usernames is None:
        usernames = []

    if valid_list:
        placeholders = ','.join(['%s'] * len(valid_list))
        sql.append(f"AND valid IN ({placeholders})")
        params.extend(valid_list)
    if user_ids:
        placeholders = ','.join(['%s'] * len(user_ids))
        sql.append(f"AND userid IN ({placeholders})")
        params.extend(user_ids)
    if usernames:
        placeholders = ','.join(['%s'] * len(usernames))
        sql.append(f"AND username IN ({placeholders})")
        params.extend(usernames)
    if username_like:
        sql.append(r"AND username LIKE %s ESCAPE '\\'")
        params.append(f"%{escape_like_pattern(username_like)}%")
    if latest_time_start:
        sql.append("AND latest_time >= %s")
        params.append(latest_time_start)
    if latest_time_end:
        sql.append("AND latest_time <= %s")
        params.append(latest_time_end)
    if scrapy_time_start:
        sql.append("AND scrapy_time >= %s")
        params.append(scrapy_time_start)
    if scrapy_time_end:
        sql.append("AND scrapy_time <= %s")
        params.append(scrapy_time_end)

    sql.append(f"ORDER BY {sort_field} {sort_direction};")
    return ' '.join(sql), tuple(params)


def get_filtered_followings(platform, valid_list=None, user_ids=None, usernames=None,
                            username_like=None,
                            latest_time_start=None, latest_time_end=None,
                            scrapy_time_start=None, scrapy_time_end=None,
                            sort_option=None):
    """
    按条件筛选 user 表关注对象。
    - valid_list: 关注类型列表，默认 [1]
    - user_ids/usernames: 可指定单个或多个 id/用户名（精确匹配）
    - username_like: 按用户名模糊匹配，适合输入部分名字
    - latest_time_* / scrapy_time_*: 按时间窗口筛选
    """
    sql, params = build_filtered_followings_query(
        ('userid', 'username', 'latest_time'),
        platform=platform,
        valid_list=valid_list,
        user_ids=user_ids,
        usernames=usernames,
        username_like=username_like,
        latest_time_start=latest_time_start,
        latest_time_end=latest_time_end,
        scrapy_time_start=scrapy_time_start,
        scrapy_time_end=scrapy_time_end,
        sort_option=sort_option,
    )
    return exec_sql_get_data(sql, params)


def get_filtered_following_rows(platform=None, valid_list=None, user_ids=None, usernames=None,
                                username_like=None,
                                latest_time_start=None, latest_time_end=None,
                                scrapy_time_start=None, scrapy_time_end=None,
                                sort_option=None):
    """读取展示模式所需的完整 user 表行。"""
    sql, params = build_filtered_followings_query(
        ('userid', 'username', 'platform', 'valid', 'latest_time', 'scrapy_time'),
        platform=platform,
        valid_list=valid_list,
        user_ids=user_ids,
        usernames=usernames,
        username_like=username_like,
        latest_time_start=latest_time_start,
        latest_time_end=latest_time_end,
        scrapy_time_start=scrapy_time_start,
        scrapy_time_end=scrapy_time_end,
        sort_option=sort_option,
    )
    return exec_sql_get_data(sql, params)


def exec_sql_get_data(sql, data=None):
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, data)
    except Exception as e:
        print(e)
        conn.rollback()
    else:
        conn.commit()
    data = [item[0] if len(item) == 1 else item for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data


def get_sent_post(douyin_weibo):
    return exec_sql_get_data('SELECT DISTINCT idstr FROM messages WHERE url LIKE %s;', (f'%{douyin_weibo}%',))


def has_sent_post(idstr):
    rows = exec_sql_get_data('SELECT 1 FROM messages WHERE idstr=%s LIMIT 1;', (idstr,))
    return bool(rows)


def get_file(url):
    return exec_sql_get_data('SELECT CAPTION FROM messages WHERE url=%s', (url,))


def get_messages(url):
    return exec_sql_get_data('SELECT MESSAGE_ID FROM messages WHERE url=%s', (url,))


def get_duplicate_caption(url):
    return exec_sql_get_data('SELECT url, CAPTION FROM messages WHERE url=%s '
                             'GROUP BY CAPTION HAVING COUNT(*) > 1;', (url,))


def delete_db_message(messages_id):
    if not messages_id:
        return None

    placeholders = ','.join(['%s'] * len(messages_id))
    sql = f'DELETE FROM messages WHERE message_id IN ({placeholders})'

    return exec_sql_get_data(sql, tuple(messages_id))


def get_duplicate_messages():
    hours_ago = datetime.datetime.now() - datetime.timedelta(hours=48)
    hours_ago = hours_ago.strftime('%Y-%m-%d %H:%M:%S')
    sql = '''SELECT DISTINCT b.url, b.caption
             FROM (SELECT CAPTION, url
                   FROM messages
                   WHERE DATE_TIME > %s
                   GROUP BY CAPTION, url
                   HAVING COUNT(*) > 1) b'''
    return exec_sql_get_data(sql, (hours_ago,))


def get_message_id(caption, url):
    return exec_sql_get_data('SELECT message_id FROM messages WHERE caption=%s AND url=%s ORDER BY MESSAGE_ID',
                             (caption, url))


def get_message_ids(message_id):
    return exec_sql_get_data('SELECT message_id FROM messages WHERE url '
                             'IN (SELECT url FROM messages WHERE message_id=%s)', (message_id,))


def get_message_url(message_id):
    return exec_sql_get_data('SELECT url FROM messages WHERE message_id=%s', (message_id,))


def get_user_by_userid(user_id):
    return exec_sql_get_data('select userid,username,latest_time from user where userid=%s', (user_id,))


def update_db(user_id, username, latest_time='', no_send=False):
    """
    默认爬取后会更新用户的scrapy_time，如果不发送 或者 没有最新作品的 latest_time 则不更新 latest_time
    """
    conn = get_db_conn()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = 'UPDATE `user` SET scrapy_time=%s'
    if latest_time and not no_send:
        sql += ', latest_time=%s WHERE USERID=%s and username=%s;'
        data = (now, latest_time, user_id, username)
    else:
        sql += ' WHERE USERID=%s and username=%s;'
        data = (now, user_id, username)
    cursor.execute(sql, data)
    conn.commit()
    cursor.close()
    conn.close()


def add_user(user_id, username, platform, valid=2):
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute('insert into user (userid, username, platform, valid) values (%s, %s, %s, %s) ',
                       (user_id, username, platform, valid))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        cursor.close()
        conn.close()


def update_user(valid, user_id):
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute('update user set valid=%s where userid=%s', (valid, user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        cursor.close()
        conn.close()
