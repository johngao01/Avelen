import asyncio
import re
from time import sleep
import emoji
import os
from telegram.constants import ParseMode

from core.database import get_db_conn
from telegram import Bot
from loguru import logger
logger.add("../logs/modify_msg.log")
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
db = get_db_conn()
tg_bot = Bot(token=TOKEN)
MARKDOWN_CHAR = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']


def update_message(url, username, message):
    conn = get_db_conn()
    message_str = message.to_json()
    with conn.cursor() as cursor:
        cursor.execute("update messages set msg_str=%s, username=%s where url=%s", (message_str, username, url,))
        conn.commit()
    conn.close()


def replace_char(text) -> str:
    for char in MARKDOWN_CHAR:
        text = text.replace(char, f'\\{char}')
    return text


def clear_name(text):
    # 去除中英文小括号及其内容
    result = re.sub(r'[（(【].*?[】)）]', '', text)
    # 去除表情
    result = emoji.demojize(result)
    result = re.sub(r':\S+?:', '', result)
    # 只保留字母、数字、下划线，其余全部删除
    result = re.sub(r'[^\w]', '', result)
    result = result.replace('_', r'\_')
    if result == '':
        return '没有名字'
    return result


async def main():
    conn = get_db_conn()
    cursor = conn.cursor()
    sql = f"select * from messages where USERID='MS4wLjABAAAArfggQM-3bXDdSKujh-vCUgR73JANC3U2RdkxNHk8GZwmMPZjgtV3FEnvUPpB8mDF'"
    username = '鹿瑶'
    logger.info(sql)
    cursor.execute(sql)
    count = 0
    data = cursor.fetchall()
    num = len(data)
    for start, message in enumerate(data, start=1):
        message_id, caption, chat_id = message[0], message[1], message[5]
        try:
            if caption is None or caption == '':
                text, id_str, url, user_id, name = message[7], message[11], message[8], message[9], message[10]
                msg = ' '.join([f'{start}/{num}',str(message_id), id_str, url, user_id])

                cleared_name = clear_name(username)
                if name == username:
                    continue
                id_str = replace_char(id_str)
                text = replace_char(text)
                _ = fr'\#{cleared_name}  [{id_str}]({url})\n\n{text}'
                try:
                    count += 1
                    result = await tg_bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=_,
                                                            parse_mode=ParseMode.MARKDOWN_V2)
                    try:
                        update_message(url, username, result)
                    except Exception as e:
                        logger.info(msg + f' 更新数据库msg_str发生错误 ' + str(e))
                    if count % 100 == 0:
                        if count % 1000 == 0:
                            sleep(600)
                        else:
                            sleep(200)
                    
                except Exception as e:
                    logger.info(msg + " 发生错误 " + str(e))
                    if 'exceeded' in str(e) or 'Flood' in str(e):
                        sleep(4000)
                else:
                    logger.info(msg + f' {cleared_name} done')
        except Exception as e:
            print(e)


asyncio.run(main())


