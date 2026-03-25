import datetime
import os
import pymysql

mysql_host = os.getenv('MYSQL_HOST', 'rn')
mysql_user = os.getenv('MYSQL_USER', 'root')
mysql_password = os.getenv('MYSQL_PASSWORD', '')
mysql_port = int(os.getenv('MYSQL_PORT', 3306))
mysql_db = os.getenv('MYSQL_DB', 'nicebot')

MESSAGES = ['MESSAGE_ID', 'CAPTION', 'CHAT_ID', 'DATE_TIME', 'FORM_USER', 'CHAT', 'MEDIA_GROUP_ID', 'TEXT_RAW',
            'URL', 'USERID', 'USERNAME', 'IDSTR', 'MBLOGID', 'MSG_STR']


def get_db_conn():
    conn = pymysql.connect(host=mysql_host,
                           user=mysql_user,
                           port=mysql_port,
                           password=mysql_password,
                           database=mysql_db)
    return conn


def insert_data(db_conn, table_name, columns, data_dict):
    cursor = db_conn.cursor()
    columns_str = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders});"
    data = [data_dict[column] for column in columns]
    cursor.execute(sql, data)
    db_conn.commit()


def get_filtered_followings(platform, valid_list=None, user_ids=None, usernames=None,
                            latest_time_start=None, latest_time_end=None,
                            scrapy_time_start=None, scrapy_time_end=None):
    """
    按条件筛选 user 表关注对象。
    - valid_list: 关注类型列表，默认 [1]
    - user_ids/usernames: 可指定单个或多个 id/用户名
    - latest_time_* / scrapy_time_*: 按时间窗口筛选
    """
    if valid_list is None:
        valid_list = [1, 2]
    if user_ids is None:
        user_ids = []
    if usernames is None:
        usernames = []

    sql = ["SELECT userid, username, latest_time FROM `user` WHERE platform=%s"]
    params = [platform]

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

    sql.append("ORDER BY scrapy_time DESC;")
    return exec_sql_get_data(' '.join(sql), tuple(params))


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


def get_file(url):
    return exec_sql_get_data('SELECT CAPTION FROM messages WHERE url=%s', (url,))


def get_messages(url):
    return exec_sql_get_data('SELECT MESSAGE_ID FROM messages WHERE url=%s', (url,))


def get_duplicate_caption(url):
    return exec_sql_get_data('SELECT url, CAPTION FROM messages WHERE url=%s '
                             'GROUP BY CAPTION HAVING COUNT(*) > 1;', (url,))


def delete_db_message(message_id):
    return exec_sql_get_data('DELETE FROM messages WHERE message_id=%s', (message_id,))


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


def update_db(user_id, username, latest_time):
    conn = get_db_conn()
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = 'UPDATE `user` SET latest_time=%s, scrapy_time=%s WHERE USERID=%s and username=%s;'
    cursor.execute(sql, (latest_time, now, user_id, username))
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


