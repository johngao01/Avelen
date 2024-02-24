import html
import sys
import traceback
from re import compile
from urllib.parse import parse_qs

import telegram.error
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageReactionHandler,
    ContextTypes, MessageHandler, filters
)

from database import *
from handler_douyin import *
from handler_weibo import *
from handler_instagram import *

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
    message_id = update.message.message_id
    text = update.message.text
    logger.info(message_id)
    logger.info(text)
    if 'scrapy' in text:
        if 'weibo' in text:
            os.system('python3 weibo_scrapy.py')
        elif 'douyin' in text:
            os.system('python3 douyin_scrapy.py')
    elif text == 'sw':
        os.system('python3 weibo_scrapy.py')
    elif text == 'sd':
        os.system('python3 douyin_scrapy.py')
    await delete_message(context, DEVELOPER_CHAT_ID, message_id)
    logger.info("scrapy end")


async def delete_message(context, chat_id, message_id):
    try:
        if type(message_id) is list:
            await context.bot.delete_messages(chat_id, message_id)
        else:
            await context.bot.delete_message(chat_id, message_id)
    except telegram.error.TelegramError as e:
        print(e)


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        await echo(update, context)
        return
    message_id = update.message.message_id
    await context.bot.send_document(document=open('/root/pythonproject/weibo_tg_bot/sqlite.db', 'rb'),
                                    chat_id=DEVELOPER_CHAT_ID, read_timeout=42, connect_timeout=20, pool_timeout=20)
    await context.bot.send_document(document=open('/etc/x-ui/x-ui.db', 'rb'), chat_id=DEVELOPER_CHAT_ID,
                                    read_timeout=42, connect_timeout=20, pool_timeout=20)
    await delete_message(context, DEVELOPER_CHAT_ID, message_id)


async def get_url(update):
    message = update.message.reply_to_message
    if not message:
        return
    logger.info("reply message id：" + str(message.id))
    text = message.text_markdown
    if text is None:
        return
    logger.info(text)
    url = re.findall(r'\((.*?)\)', text)
    if not url:
        return
    url = url[0]
    logger.info(url)
    return url


async def del_files(weibo_files):
    for root, dirs, files in os.walk("/root/download"):
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
        files = get_file(url)
        messages = get_messages(url)
        messages.append(message_id)
        await del_files(files)
    else:
        messages = [message_id]
    print(messages)
    await delete_message(context, DEVELOPER_CHAT_ID, messages)
    return url


async def resend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = await delete(update, context)
    if url:
        if 'weibo' in url:
            r = handle_weibo(url)
            store_message_data(r)
        elif 'douyin' in url:
            link, aweme_id = get_url_id(url)
            aweme = get_aweme_detail(aweme_id)
            handler_douyin(aweme)
        else:
            pass


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    url = await get_url(update)
    if url:
        duplicate = get_duplicate_caption(url)
    else:
        duplicate = get_duplicate_messages()
    if len(duplicate) > 0:
        for url, caption in duplicate:
            message_ids = get_message_id(caption, url)
            if len(message_ids) > 0:
                delete_messages = message_ids[0:-1]
                print(message_ids, delete_messages)
                for mid in delete_messages:
                    delete_db_message(mid)
                await delete_message(context, DEVELOPER_CHAT_ID, delete_messages)
    await delete_message(context, DEVELOPER_CHAT_ID, message_id)


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
    await delete_message(context, DEVELOPER_CHAT_ID, message_id)


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
    logger.error(message)
    # Finally, send the message
    # await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)
    # await context.bot.send_message(chat_id=update.effective_chat.id, text="抱歉，出现了一些错误，无法获得相应的内容")


async def edit_commands(application):
    command = [BotCommand("backup", "备份数据"),
               BotCommand("clear", "清理"),
               BotCommand("resend", "重发"),
               BotCommand("delete", "删除")
               ]
    await application.bot.set_my_commands(commands=command)
    print("bot start ------------------->")
    # await application.bot.send_message(text="bot begin start", chat_id=DEVELOPER_CHAT_ID)


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
        for clarity in ['FULL_HD1', 'HD1', 'SD1', 'SD2']:
            if clarity in stream_urls:
                await context.bot.send_message(text=stream_urls[clarity], chat_id=update.effective_chat.id)
                break
        await context.bot.send_message(update.effective_chat.id, '\t'.join([nickname, title, str(viewer)]))

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
    link, aweme_id = get_url_id(link_message)
    if aweme_id == '':
        await live_douyin(update, context)
        return
    logger.info(link)
    aweme = get_aweme_detail(aweme_id)
    if aweme is None:
        logger.error(f"处理抖音 {link} 失败")
        await delete_message(context, DEVELOPER_CHAT_ID, message_id)
        return
    if handler_douyin(aweme):
        pass
    else:
        logger.error(f"处理抖音 {link} 失败")
    await delete_message(context, DEVELOPER_CHAT_ID, message_id)


async def reaction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messages_id = []
    reaction = update.message_reaction
    print(reaction.old_reaction, reaction.new_reaction)
    emoji = reaction.new_reaction[0].emoji
    reaction_message_id = reaction.message_id
    if emoji == '👎' or emoji == "😁":
        messages_id = get_message_ids(reaction_message_id)
        print(messages_id)
        await delete_message(context, DEVELOPER_CHAT_ID, messages_id)
    if emoji == "😁":
        url = get_message_url(reaction_message_id)
        if url:
            url = url[0]
            logger.info("url：" + url)
            files = get_file(url)
            await del_files(files)
            for message_id in messages_id:
                delete_db_message(message_id)
            if 'weibo' in url:
                r = handle_weibo(url)
                store_message_data(r)
            elif 'douyin' in url:
                link, aweme_id = get_url_id(url)
                aweme = get_aweme_detail(aweme_id)
                handler_douyin(aweme)
            else:
                pass


async def instagram_scrapy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link_message = update.message.text
    message_id = update.message.message_id
    shortcode = link_message.split('/')[4]
    logger.info(shortcode)
    post = get_post_detail(shortcode)
    if post is None:
        logger.error(f"处理instagram {link_message} 失败")
        await delete_message(context, DEVELOPER_CHAT_ID, message_id)
        return
    r = handler_post(Post(post['data']['xdt_api__v1__media__shortcode__web_info']['items'][0]))
    if type(r) is requests.Response:
        if r.status_code == 200:
            store_message_data(r)
        else:
            logger.error(f"处理instagram {link_message} 失败")
    else:
        logger.error(f"处理instagram {link_message} 失败")
    await delete_message(context, DEVELOPER_CHAT_ID, message_id)


def main() -> None:
    weibo_filter = filters.Regex('^https://(m.|www.)?weibo(.cn|.com)?/[0-9]+/*')
    douyin_filter = filters.Regex('https://(v.|www.|live.)?(ies)?douyin.*')
    instagram_filter = filters.Regex('https://www.instagram.com/*')
    # application = Application.builder().token('6572044525:AAH6eRwxAhmhDQo7R7COrWBrZKtG6TqO1rU').post_init(
    #     edit_commands).build()
    builder = Application.builder()
    builder.token('6572044525:AAH6eRwxAhmhDQo7R7COrWBrZKtG6TqO1rU')
    builder.post_init(edit_commands)
    builder.http_version('1.1')
    builder.get_updates_http_version('1.1')
    builder.base_url(r'http://localhost:8081/bot')
    builder.base_file_url(r'http://localhost:8081/file/bot')
    builder.local_mode(local_mode=True)
    application = builder.build()
    application.add_handler(MessageReactionHandler(reaction_handler))
    application.add_handler(CommandHandler("backup", backup))
    application.add_handler(CommandHandler("resend", resend))
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(MessageHandler(weibo_filter, weibo_scrapy))
    application.add_handler(MessageHandler(douyin_filter, douyin_scrapy))
    application.add_handler(MessageHandler(instagram_filter, instagram_scrapy))
    application.add_handler(
        MessageHandler(filters.Text() & (~douyin_filter or ~weibo_filter or ~instagram_filter), echo))
    application.add_error_handler(error_handler)
    application.run_polling()


if __name__ == "__main__":
    main()
