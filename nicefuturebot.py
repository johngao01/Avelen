import html
import re
import sys

from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes, MessageHandler, filters,
)

from database import *
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


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        await echo(update, context)
        return
    await context.bot.send_document(document=open('/root/pythonproject/weibo_tg_bot/weibo.sqlite.db', 'rb'),
                                    chat_id=DEVELOPER_CHAT_ID)


async def get_weibo_url(update):
    message = update.message.reply_to_message
    if not message:
        return
    text = message.text_markdown
    weibo_url = re.findall(r'\((.*?)\)', text)
    if not weibo_url:
        return
    weibo_url = weibo_url[0]
    logger.info(weibo_url)
    return weibo_url


async def del_weibo_files(weibo_files):
    for root, dirs, files in os.walk("/root/download/weibo"):
        for file in files:
            if file in weibo_files:
                path = os.path.join(root, file)
                logger.info("删除文件：" + path)
                os.remove(path)


async def delete_weibo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    weibo_url = await get_weibo_url(update)
    weibo_files = get_weibo_file(weibo_url)
    weibo_messages = get_weibo_messages(weibo_url)
    weibo_messages.append(message_id)
    await del_weibo_files(weibo_files)
    for message_id in weibo_messages:
        await context.bot.delete_message(chat_id=DEVELOPER_CHAT_ID, message_id=message_id)
        logger.info(f"删除id为{message_id}的message")
    delete_weibo_data(weibo_url)


async def resend_weibo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    weibo_url = await delete_weibo(update, context)
    r = handle_weibo(weibo_url)
    store_message_data(r)


async def weibo_scrapy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    weibo_link = update.message.text
    logger.info(weibo_link)
    r = handle_weibo(weibo_link)
    store_message_data(r)


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
    message = await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)
    store_message_data(message)
    message = await context.bot.send_message(chat_id=update.effective_chat.id,
                                             text="抱歉，出现了一些错误，无法获得相应的内容")
    store_message_data(message)


async def edit_commands(application):
    command = [BotCommand("backup", "备份数据"), BotCommand("resend_weibo", "重发微博"),
               BotCommand("delete_weibo", "删除微博")]
    await application.bot.set_my_commands(commands=command)
    # await application.bot.send_message(text="bot begin start", chat_id=DEVELOPER_CHAT_ID)


def main() -> None:
    weibo_filter = filters.Regex('^https://(m.|www.)?weibo(.cn|.com)?/[0-9]+/*')
    application = Application.builder().token('6572044525:AAH6eRwxAhmhDQo7R7COrWBrZKtG6TqO1rU').post_init(
        edit_commands).build()
    application.add_handler(CommandHandler("backup", backup))
    application.add_handler(CommandHandler("resend_weibo", resend_weibo))
    application.add_handler(CommandHandler("delete_weibo", delete_weibo))
    application.add_handler(MessageHandler(weibo_filter, weibo_scrapy))
    application.add_error_handler(error_handler)
    application.run_polling()


if __name__ == "__main__":
    main()
