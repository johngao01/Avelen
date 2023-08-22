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
    sql = f'''SELECT userid, username, scrapy_type, latest_time FROM FOLLOWINGS where douyin_weibo='{platform}';'''
    cursor.execute(sql)
    data = [item for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data


def exec_sql_get_data(sql):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(sql)
    data = [item[0] for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data


def get_send_url(douyin_weibo):
    return exec_sql_get_data(f'''SELECT distinct url FROM messages where url like '%{douyin_weibo}%';''')


def get_weibo_file(url):
    return exec_sql_get_data(f"select CAPTION from messages where url='{url}'")


def get_weibo_messages(url):
    return exec_sql_get_data(f"select MESSAGE_ID from messages where url='{url}'")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    with open('database.ddl', mode='a', encoding='utf-8') as f:
        sql = f.read()
    cursor.execute(sql)
    cursor.close()
    conn.close()
    conn.commit()


def update_db(user_id, latest_time):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    sql = f'UPDATE FOLLOWINGS SET latest_time={repr(latest_time)} WHERE USERID={repr(user_id)}'
    # print(sql)
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()

