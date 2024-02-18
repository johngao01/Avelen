import datetime
import sqlite3

DB_NAME = 'sqlite.db'


def store_message_data(response):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    response = response.json()
    messages = response['messages']
    for message in messages:
        insert_statement = """
            INSERT INTO messages (MESSAGE_ID, CAPTION, CHAT_ID, DATE_TIME, FORM_USER, CHAT, MEDIA_GROUP_ID, TEXT_RAW, 
            URL, USERID, IDSTR, MBLOGID) VALUES (:MESSAGE_ID, :CAPTION, :CHAT_ID, :DATE_TIME, :FORM_USER,
            :CHAT,:MEDIA_GROUP_ID,:TEXT_RAW,:URL,:USERID,:IDSTR,:MBLOGID)"""
        cursor.execute(insert_statement, message)
        if message['VIDEO']:
            insert_statement = """INSERT INTO video (file_id, file_unique_id, width, height, duration, file_size, 
            file_name, file_type, message_id, media_group_id, url) VALUES (:file_id, :file_unique_id, :width, 
            :height, :duration, :file_size, :file_name, :file_type, :message_id, :media_group_id, :url)"""
            cursor.execute(insert_statement, message['VIDEO'])
        if message['PHOTO']:
            for k, v in message['PHOTO'].items():
                insert_statement = """INSERT INTO photo (file_id, file_unique_id, width, height, file_size, file_name, 
                message_id, media_group_id, url) VALUES (:file_id, :file_unique_id, :width, :height, :file_size, 
                :file_name, :message_id, :media_group_id, :url)"""
                cursor.execute(insert_statement, v)
        if message['DOCUMENT']:
            insert_statement = """INSERT INTO DOCUMENT (file_id, file_unique_id, file_size, file_name, file_type, 
            message_id, media_group_id, url) VALUES (:file_id, :file_unique_id,:file_size, :file_name, :file_type, 
            :message_id, :media_group_id, :url)"""
            cursor.execute(insert_statement, message['DOCUMENT'])
    conn.commit()
    cursor.close()
    conn.close()


def get_all_following(platform):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    sql = f'''SELECT userid, username, scrapy_type, latest_time 
              FROM FOLLOWINGS 
              where douyin_weibo='{platform}' order by scrapy_time;'''
    cursor.execute(sql)
    data = [item for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data


def exec_sql_get_data(sql):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    print(sql)
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
    five_hours_ago = datetime.datetime.now() - datetime.timedelta(hours=17)
    five_hours_ago = five_hours_ago.strftime('%Y-%m-%d %H:%M:%S')
    sql = f'''select distinct url,caption from (select CAPTION, url from messages 
              where DATE_TIME > '{five_hours_ago}'
              GROUP BY CAPTION,url HAVING COUNT(*) > 1)'''
    print(sql)
    return exec_sql_get_data(sql)


def get_message_id(caption, url):
    return exec_sql_get_data(f"SELECT message_id,date_time FROM messages where caption='{caption}' and url='{url}'"
                             f" order by MESSAGE_ID")


def get_message_ids(message_id):
    return exec_sql_get_data("select message_id from messages where url "
                             f"in (select url from messages where message_id={message_id})")


def get_message_url(message_id):
    return exec_sql_get_data(f"select url from messages where message_id={message_id}")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    with open('database.ddl', mode='a', encoding='utf-8') as f:
        sql = f.read()
    cursor.execute(sql)
    cursor.close()
    conn.close()
    conn.commit()


def update_db(user_id, username, latest_time):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = (f'UPDATE FOLLOWINGS SET latest_time={repr(latest_time)},scrapy_time={repr(now)} '
           f'WHERE USERID={repr(user_id)} and username={repr(username)};')
    # print(sql)
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
