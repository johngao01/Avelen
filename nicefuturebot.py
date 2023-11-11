import html
import re
import sys
from re import compile
from urllib.parse import parse_qs
from urllib.parse import urlparse

import telegram.error
from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes, MessageHandler, filters,
)

from database import *
from handler_douyin import *
from handler_weibo import *

DEVELOPER_CHAT_ID = 708424141
script_path = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_path)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 再创建一个handler，用于输出到控制台
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)

# 定义handler的输出格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 给logger添加handler
logger.addHandler(ch)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)


async def delete_message(context, message_id, chat_id):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except telegram.error.TelegramError:
        pass


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        await echo(update, context)
        return
    message_id = update.message.message_id
    await context.bot.send_document(document=open('/root/pythonproject/weibo_tg_bot/sqlite.db', 'rb'),
                                    chat_id=DEVELOPER_CHAT_ID)
    await delete_message(context, message_id=message_id, chat_id=DEVELOPER_CHAT_ID)


async def get_url(update):
    message = update.message.reply_to_message
    if not message:
        return
    text = message.text_markdown
    logger.info(text)
    url = re.findall(r'\((.*?)\)', text)
    if not url:
        return
    url = url[0]
    logger.info(url)
    return url


async def del_weibo_files(weibo_files):
    for root, dirs, files in os.walk("/root/download/weibo"):
        for file in files:
            if file in weibo_files:
                path = os.path.join(root, file)
                logger.info("删除文件：" + path)
                os.remove(path)


async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    url = await get_url(update)
    if url:
        logger.info("url：" + url)
        weibo_files = get_weibo_file(url)
        weibo_messages = get_weibo_messages(url)
        weibo_messages.append(message_id)
        await del_weibo_files(weibo_files)
    else:
        weibo_messages = [message_id]
    for message_id in weibo_messages:
        await delete_message(context, message_id, DEVELOPER_CHAT_ID)
        logger.info(f"删除id为{message_id}的message")
    return url


async def resend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = await delete(update, context)
    if url:
        if 'weibo' in url:
            r = handle_weibo(url)
            store_message_data(r)
        elif 'douyin' in url:
            pass
        else:
            pass


async def weibo_scrapy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    weibo_link = update.message.text
    message_id = update.message.message_id
    logger.info(weibo_link)
    r = handle_weibo(weibo_link)
    if type(r) is requests.Response:
        if r.status_code == 200:
            store_message_data(r)
        else:
            logger.error(f"处理微博 {weibo_link} 失败")
    else:
        logger.error(f"处理微博 {weibo_link} 失败")
    await delete_message(context, message_id, DEVELOPER_CHAT_ID)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Finally, send the message
    await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="抱歉，出现了一些错误，无法获得相应的内容")


async def start_scrapy_douyin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    logger.info(message_id)
    logger.info("start scrapy douyin")
    os.system('python3 douyin_scrapy.py')
    await delete_message(context, message_id, DEVELOPER_CHAT_ID)
    logger.info("scrapy douyin end")


async def edit_commands(application):
    command = [BotCommand("backup", "备份数据"), BotCommand("resend", "重发"),
               BotCommand("delete", "删除"), BotCommand("scrapy_douyin", "开始爬取抖音")]
    await application.bot.set_my_commands(commands=command)
    await application.bot.send_message(text="bot begin start", chat_id=DEVELOPER_CHAT_ID)


async def live_douyin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async def get_live_data(params, api):
        new_xb = NewXBogus()
        params['X-Bogus'] = new_xb.get_x_bogus(params, ((86, 138), (238, 238,)), 23)
        if not share:
            live_headers.update({'Cookie': cookies})
        response = requests.get(api, params=params, headers=live_headers)
        if response.text == '':
            return
        data = response.json()
        data = data["data"]["room"] if share else data["data"]["data"][0]
        if data["status"] == 4:
            await context.bot.send_message(text="当前直播已结束", chat_id=update.effective_chat.id)
            return
        nickname = data["owner"]["nickname"]
        title = data["title"]
        stream_urls = data["stream_url"]["flv_pull_url"]
        viewer = data['user_count'] if 'user_count' in data else data['room_view_stats']['display_value']
        await context.bot.send_message(text='\t'.join([nickname, title, str(viewer)]), chat_id=update.effective_chat.id)
        for clarity in ['FULL_HD1', 'HD1', 'SD1', 'SD2']:
            if clarity in stream_urls:
                await context.bot.send_message(text=stream_urls[clarity], chat_id=update.effective_chat.id)
                break

    async def get_share_live_data():
        response = requests.get(link, headers=live_headers, allow_redirects=False)
        params = urlparse(response.headers['Location'])
        url_list = params.path.rstrip("/").split("/")
        query_params = parse_qs(params.query)
        room_id = url_list[-1]
        user_sec_id = query_params.get('sec_user_id', '')
        params = {
            "type_id": "0",
            "live_id": "1",
            "room_id": room_id,
            "sec_user_id": user_sec_id[0],
            "app_id": "1128",
        }
        await get_live_data(params, live_share_api)

    async def get_live_url_data(room_id):
        params = {
            "aid": "6383",
            "app_name": "douyin_web",
            "device_platform": "web",
            "cookie_enabled": "true",
            "web_rid": room_id,
        }
        await get_live_data(params, live_api)

    share = True
    share_text = update.message.text
    share_link = compile(r".*?(https://v\.douyin\.com/[A-Za-z0-9]+?/).*?")
    live_link = compile(r".*?https://live\.douyin\.com/([0-9]+).*?")  # 直播链接
    live_api = "https://live.douyin.com/webcast/room/web/enter/"  # 直播API
    live_share_api = "https://webcast.amemv.com/webcast/room/reflow/info/"  # 直播分享短链接API
    live_headers = {
        "User-Agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.183',
    }
    link = share_link.findall(share_text)
    if link:
        link = link[0]
        await get_share_live_data()
    else:
        live_room_id = live_link.findall(share_text)
        if live_room_id:
            share = False
            live_room_id = live_room_id[0]
            await get_live_url_data(live_room_id)


async def douyin_scrapy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link_message = update.message.text
    message_id = update.message.message_id
    if link_message.startswith("https://www.") or link_message.startswith("https://live."):
        link = link_message
        logger.info(link)
        if link.startswith('https://live.douyin.com/'):
            await live_douyin(update, context)
            return
        aweme_id = re.search(r'(\d{19})', link_message).group(1)
    else:
        link = re.search('https://v.douyin.com/[A-Za-z0-9]+/', link_message).group(0)
        r = requests.get(url=link, headers=headers, allow_redirects=False)
        link = r.headers.get('Location')
        logger.info(link)
        if link.startswith('https://webcast.amemv.com/douyin/webcast/reflow/'):
            await live_douyin(update, context)
            return
        aweme_id = re.search(r'https://www.iesdouyin.com/share/(video|note)/(\d{19})/?', link).group(2)
    logger.info(link)
    params = {
        "aweme_id": aweme_id,
        "aid": "6383",
        "cookie_enabled": "true",
        "platform": "PC",
        "downlink": "10"
    }
    new_xb = NewXBogus()
    params['X-Bogus'] = new_xb.get_x_bogus(params, ((86, 138), (238, 238,)), 23)
    api_post_url = 'https://www.douyin.com/aweme/v1/web/aweme/detail/?'
    rs = requests.get(api_post_url, params=params, headers=douyin_headers, timeout=5)
    if rs.text == '':
        logger.error(f"处理抖音 {link} 失败")
        await context.bot.send_message(update.effective_chat.id, "获取失败")
        return
    response_json = json.loads(rs.text)
    aweme = response_json['aweme_detail']
    aweme['create_time'] = datetime.fromtimestamp(aweme['create_time'])
    user = Following(aweme['author']['sec_uid'], aweme['author']['nickname'], 1, '')
    aweme = Aweme(user, aweme)
    if aweme.is_video:
        r = handler_video_douyin(aweme)
    else:
        r = handler_note_douyin(aweme)
    if type(r) is requests.Response:
        if r.status_code == 200:
            store_message_data(r)
        else:
            logger.error(f"处理抖音 {link} 失败")
    else:
        logger.error(f"处理抖音 {link} 失败")
    await delete_message(context, message_id, DEVELOPER_CHAT_ID)


def main() -> None:
    weibo_filter = filters.Regex('^https://(m.|www.)?weibo(.cn|.com)?/[0-9]+/*')
    douyin_filter = filters.Regex('https://(v.|www.|live.)?douyin.*')
    application = Application.builder().token('6572044525:AAH6eRwxAhmhDQo7R7COrWBrZKtG6TqO1rU').post_init(
        edit_commands).build()
    application.add_handler(CommandHandler("backup", backup))
    application.add_handler(CommandHandler("resend", resend))
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CommandHandler("scrapy_douyin", start_scrapy_douyin))
    application.add_handler(MessageHandler(weibo_filter, weibo_scrapy))
    application.add_handler(MessageHandler(douyin_filter, douyin_scrapy))
    application.add_error_handler(error_handler)
    application.run_polling()


if __name__ == "__main__":
    main()
