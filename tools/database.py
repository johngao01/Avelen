import datetime
import os
import pymysql

# mysql_host = '38.49.57.25'
mysql_host = os.getenv('MYSQL_HOST', 'localhost')
mysql_user = os.getenv('MYSQL_USER', 'root')
mysql_password = os.getenv('MYSQL_PASSWORD', '')
mysql_port = int(os.getenv('MYSQL_PORT', 3306))
mysql_db = os.getenv('MYSQL_DB', 'nicebot')

MESSAGES = ['MESSAGE_ID', 'CAPTION', 'CHAT_ID', 'DATE_TIME', 'FORM_USER', 'CHAT', 'MEDIA_GROUP_ID', 'TEXT_RAW',
            'URL', 'USERID', 'USERNAME', 'IDSTR', 'MBLOGID', 'MSG_STR']
VIDEO = ['file_id', 'file_unique_id', 'width', 'height', 'duration', 'file_size',
         'file_name', 'file_type', 'message_id', 'media_group_id', 'url']

PHOTO = ['file_id', 'file_unique_id', 'width', 'height', 'file_size', 'file_name',
         'message_id', 'media_group_id', 'url']

DOCUMENT = ['file_id', 'file_unique_id', 'file_size', 'file_name', 'file_type',
            'message_id', 'media_group_id', 'url']


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


def store_message_data(response):
    conn = get_db_conn()
    cursor = conn.cursor()
    response = response.json()
    messages = response['messages']
    for message in messages:
        insert_data(conn, 'messages', MESSAGES, message)
        if message['VIDEO']:
            insert_data(conn, 'video', VIDEO, message['VIDEO'])
        if message['PHOTO']:
            for k, v in message['PHOTO'].items():
                insert_data(conn, 'photo', PHOTO, v)
        if message['DOCUMENT']:
            insert_data(conn, 'document', DOCUMENT, message['DOCUMENT'])
    conn.commit()
    cursor.close()
    conn.close()


def get_all_following(platform, valid=1):
    conn = get_db_conn()
    cursor = conn.cursor()
    sql = '''SELECT userid, username, latest_time 
             FROM `user`
             WHERE platform=%s AND valid=%s ORDER BY scrapy_time DESC;'''
    cursor.execute(sql, (platform, valid))
    data = [item for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data


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


def get_send_url(douyin_weibo):
    return exec_sql_get_data('SELECT DISTINCT url FROM messages WHERE url LIKE %s;', (f'%{douyin_weibo}%',))


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
    sql = '''SELECT DISTINCT b.url, b.caption FROM (
                SELECT CAPTION, url FROM messages
                WHERE DATE_TIME > %s
                GROUP BY CAPTION, url HAVING COUNT(*) > 1
             ) b'''
    return exec_sql_get_data(sql, (hours_ago,))


def get_message_id(caption, url):
    return exec_sql_get_data('SELECT message_id FROM messages WHERE caption=%s AND url=%s ORDER BY MESSAGE_ID',
                             (caption, url))


def get_message_ids(message_id):
    return exec_sql_get_data('SELECT message_id FROM messages WHERE url '
                             'IN (SELECT url FROM messages WHERE message_id=%s)', (message_id,))


def get_message_url(message_id):
    return exec_sql_get_data('SELECT url FROM messages WHERE message_id=%s', (message_id,))


def init_db():
    conn = get_db_conn()
    cursor = conn.cursor()
    with open('database.ddl', mode='a', encoding='utf-8') as f:
        sql = f.read()
    cursor.execute(sql)
    cursor.close()
    conn.close()
    conn.commit()


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
