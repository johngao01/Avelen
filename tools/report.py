import asyncio

import pymysql
import pandas as pd
from datetime import datetime

from telegram import Bot


def niceme_report(report_day):
    conn = pymysql.connect(
        host="38.49.57.25",
        user="root",
        password="31305a0fbd",
        database="nicebot",
        charset="utf8mb4"
    )

    sql = """SELECT CAPTION, DATE_TIME, URL, USERID, USERNAME, IDSTR
             FROM messages
             WHERE DATE(DATE_ADD(DATE_TIME, INTERVAL 8 HOUR)) = %s"""
    df = pd.read_sql(sql, conn, params=[report_day])
    conn.close()
    if df.empty:
        return "当天没有数据"
    total_messages = len(df)
    user_count = df["USERID"].nunique()
    work_count = df["IDSTR"].nunique()

    def count_files(captions):
        image_count = 0
        video_count = 0
        for caption in captions:
            if caption:
                if caption.endswith((".jpg", ".jpeg", ".gif", ".png")):
                    image_count += 1
                elif caption.endswith((".mp4", ".mov")):
                    video_count += 1
                else:
                    pass
        return image_count, video_count

    file_count = count_files(df["CAPTION"])

    def detect_platform(url):
        if not isinstance(url, str):
            return "other"
        if "weibo.com" in url:
            return "微博"
        if "douyin.com" in url:
            return "抖音"
        if "instagram.com" in url:
            return "Instagram"
        return "other"

    df["platform"] = df["URL"].apply(detect_platform)
    platform_stats = (
        df.dropna(subset=["URL"])
        .drop_duplicates(subset=["URL"])
        .groupby("platform")["URL"]
        .count()
        .sort_values(ascending=False)
    )

    result = f"""#niceme统计信息
<b>日期</b>：{report_day}
<b>消息总数</b>：{total_messages}
<b>用户数量</b>：{user_count}    <b>作品数量</b>：{work_count}
<b>图片数量</b>：{file_count[0]}    <b>视频数量</b>：{file_count[1]}
"""
    for k, v in platform_stats.items():
        result += f"<b>{k}</b>: {v} "
    return result


def tiktok_report(report_day):
    conn = pymysql.connect(
        host="104.224.157.239",
        user="root",
        password="31305a0fbd",
        database="tiktok_bot",
        charset="utf8mb4"
    )
    cursor = conn.cursor()
    cursor.execute("select count(*) from aweme where DATE(DATE_ADD(SCRAPY_AT, INTERVAL 8 HOUR))=%s", (report_day))
    # 当天爬取的aweme数量
    report_day_scrapy_aweme_num = cursor.fetchone()[0]
    cursor.execute(
        "select count(distinct chat_id) from (select * from messages where DATE(DATE_ADD(`DATE_TIME`, INTERVAL 8 HOUR))=%s) a",
        (report_day,))
    # 当天使用bot的用户数
    report_day_bot_user_num = cursor.fetchone()[0]
    cursor.execute(
        "select count(distinct chat_id) from (select * from `users` where DATE(DATE_ADD(created_at, INTERVAL 8 HOUR))=%s) a",
        (report_day,))
    # 当天新增的bot的用户数
    report_day_bot_new_user = cursor.fetchone()[0]
    result = f"""#tiktok_bot统计信息
<b>日期</b>：{report_day}
<b>当天爬取的aweme数量</b>：{report_day_scrapy_aweme_num}
<b>当天使用bot的用户数</b>：{report_day_bot_user_num}
<b>当天新增的bot的用户数</b>：{report_day_bot_new_user}
"""
    return result


async def main(report_day):
    DEVELOPER_CHAT_ID = 708424141
    TOKEN = '5355419947:AAEHOGlkz7hlOO38XRRZ9vVhtAnVGjwbjKw'
    API_URL = 'http://localhost:8081/bot'
    FILE_API_URL = 'http://localhost:8081/file/bot'
    bot = Bot(token=TOKEN, local_mode=True, base_url=API_URL, base_file_url=FILE_API_URL)
    niceme_report_data = niceme_report(report_day)
    await bot.send_message(DEVELOPER_CHAT_ID, niceme_report_data, parse_mode='html')
    tiktok_report_data = tiktok_report(report_day)
    await bot.send_message(DEVELOPER_CHAT_ID, tiktok_report_data, parse_mode='html')


if __name__ == '__main__':
    today = datetime.today().strftime("%Y-%m-%d")
    asyncio.run(main(today))
