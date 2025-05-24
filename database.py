import datetime
import pymysql

# mysql_host = '38.49.57.25'
mysql_host = 'localhost'
mysql_user = 'root'
mysql_password = '31305a0fbd'
mysql_port = 3306
mysql_db = 'nicebot'

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


def get_all_following(platform):
    conn = get_db_conn()
    cursor = conn.cursor()
    sql = f'''SELECT userid, username, latest_time 
              FROM `user`
              where platform='{platform}' and valid=1 order by scrapy_time;'''
    cursor.execute(sql)
    data = [item for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data


def exec_sql_get_data(sql):
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
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
    return exec_sql_get_data(f'''SELECT distinct url FROM messages where url like '%{douyin_weibo}%';''')


def get_file(url):
    return exec_sql_get_data(f"select CAPTION from messages where url='{url}'")


def get_messages(url):
    return exec_sql_get_data(f"select MESSAGE_ID from messages where url='{url}'")


def get_duplicate_caption(url):
    return exec_sql_get_data(f"SELECT url,CAPTION FROM messages where url='{url}'"
                             f"GROUP BY CAPTION HAVING COUNT(*) > 1;")


def delete_db_message(message_id):
    return exec_sql_get_data(f"delete FROM messages where message_id='{message_id}'")


def get_duplicate_messages():
    hours_ago = datetime.datetime.now() - datetime.timedelta(hours=48)
    hours_ago = hours_ago.strftime('%Y-%m-%d %H:%M:%S')
    sql = f'''select distinct b.url,b.caption from (select CAPTION, url from messages 
              where DATE_TIME > '{hours_ago}'
              GROUP BY CAPTION,url HAVING COUNT(*) > 1) b'''
    return exec_sql_get_data(sql)


def get_message_id(caption, url):
    return exec_sql_get_data(f"SELECT message_id FROM messages where caption='{caption}' and url='{url}'"
                             f" order by MESSAGE_ID")


def get_message_ids(message_id):
    return exec_sql_get_data("select message_id from messages where url "
                             f"in (select url from messages where message_id={message_id})")


def get_message_url(message_id):
    return exec_sql_get_data(f"select url from messages where message_id={message_id}")


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
    sql = (f'UPDATE `user` SET latest_time={repr(latest_time)},scrapy_time={repr(now)} '
           f'WHERE USERID={repr(user_id)} and username={repr(username)};')
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()


def add_user(user_id, username, platform):
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute('insert into user (userid, username, platform) values (%s, %s, %s) ', (user_id, username, platform))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        cursor.close()
        conn.close()

def remove_user(user_id,):
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute('update user set valid=0 where userid=%s', (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        cursor.close()
        conn.close()
