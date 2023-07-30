import sqlite3

DB_NAME = 'weibo.sqlite.db'


def store_message_data(response):
    conn = sqlite3.connect('weibo.sqlite.db')
    cursor = conn.cursor()
    response = response.json()
    messages = response['messages']
    for message in messages:
        insert_statement = """
            INSERT INTO messages (MESSAGE_ID, CAPTION, CHAT_ID, DATE_TIME, FORM_USER, CHAT, MEDIA_GROUP_ID, TEXT_RAW, 
            WEIBO_URL, USERID, WEIBO_IDSTR, MBLOGID) VALUES (:MESSAGE_ID, :CAPTION, :CHAT_ID, :DATE_TIME, :FORM_USER,
            :CHAT,:MEDIA_GROUP_ID,:TEXT_RAW,:WEIBO_URL,:USERID,:WEIBO_IDSTR,:MBLOGID)"""
        cursor.execute(insert_statement, message)
        if message['VIDEO']:
            insert_statement = """INSERT INTO video (file_id, file_unique_id, width, height, duration, file_size, 
            file_name, file_type, message_id, media_group_id, weibo_url) VALUES (:file_id, :file_unique_id, :width, 
            :height, :duration, :file_size, :file_name, :file_type, :message_id, :media_group_id, :weibo_url)"""
            cursor.execute(insert_statement, message['VIDEO'])
        if message['PHOTO']:
            for k, v in message['PHOTO'].items():
                insert_statement = """INSERT INTO photo (file_id, file_unique_id, width, height, file_size, file_name, 
                message_id, media_group_id, weibo_url) VALUES (:file_id, :file_unique_id, :width, :height, :file_size, 
                :file_name, :message_id, :media_group_id, :weibo_url)"""
                cursor.execute(insert_statement, v)
        if message['DOCUMENT']:
            insert_statement = """INSERT INTO DOCUMENT (file_id, file_unique_id, file_size, file_name, file_type, 
            message_id, media_group_id, weibo_url) VALUES (:file_id, :file_unique_id,:file_size, :file_name, :file_type, 
            :message_id, :media_group_id, :weibo_url)"""
            cursor.execute(insert_statement, message['DOCUMENT'])
    conn.commit()
    cursor.close()
    conn.close()


def get_all_following():
    conn = sqlite3.connect('weibo.sqlite.db')
    cursor = conn.cursor()
    sql = '''SELECT * FROM FOLLOWINGS;'''
    cursor.execute(sql)
    data = [item for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data


def get_send_weibo():
    conn = sqlite3.connect('weibo.sqlite.db')
    cursor = conn.cursor()
    sql = '''SELECT distinct weibo_url FROM messages;'''
    cursor.execute(sql)
    data = [item[0] for item in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data


def init_db():
    conn = sqlite3.connect('weibo.sqlite.db')
    cursor = conn.cursor()
    with open('database.ddl', mode='a', encoding='utf-8') as f:
        sql = f.read()
    cursor.execute(sql)
    cursor.close()
    conn.close()
    conn.commit()


def update_db(user_id, latest_weibo_time):
    conn = sqlite3.connect('weibo.sqlite.db')
    cursor = conn.cursor()
    sql = f'UPDATE FOLLOWINGS SET LAST_WEIBO_TIME={repr(latest_weibo_time)} WHERE USERID={repr(user_id)}'
    print(sql)
    cursor.execute(sql)
    conn.commit()
    cursor.close()
    conn.close()
