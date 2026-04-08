import html
import traceback
import telegram.error
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageReactionHandler,
    ContextTypes, MessageHandler, filters
)

from core.database import *
from loguru import logger
import re
import json

DEVELOPER_CHAT_ID = 708424141


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    text = update.message.text
    logger.info(message_id)
    logger.info(text)
    if 'scrapy' in text:
        if 'weibo' in text:
            os.system('python main.py weibo')
        elif 'douyin' in text:
            os.system('python main.py douyin')
    elif text == 'sw':
        os.system('python main.py weibo')
    elif text == 'sd':
        os.system('python main.py douyin')
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


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    url = await get_url(update)
    if url:
        duplicate = get_duplicate_caption(url)
    else:
        duplicate = get_duplicate_messages()
    if len(duplicate) > 0:
        print(f"共有{len(duplicate)}个记录")
        for url, caption in duplicate:
            message_ids = get_message_id(caption, url)
            if len(message_ids) > 0:
                delete_messages = message_ids[0:-1]
                print(url, caption, message_ids, delete_messages)
                for mid in delete_messages:
                    delete_db_message(mid)
                await delete_message(context, DEVELOPER_CHAT_ID, delete_messages)
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
    command = [BotCommand("clear", "清理"),
               BotCommand("delete", "删除")]
    await application.bot.set_my_commands(commands=command)
    print("bot start ------------------->")
    # await application.bot.send_message(text="bot begin start", chat_id=DEVELOPER_CHAT_ID)


async def reaction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messages_id = []
    reaction = update.message_reaction
    print(reaction.old_reaction, reaction.new_reaction)
    emoji = reaction.new_reaction or reaction.old_reaction
    if emoji:
        emoji = emoji[0].emoji
    else:
        return
    reaction_message_id = reaction.message_id
    if emoji == '👎' or emoji == "😁":
        print(reaction_message_id)
        messages_id = get_message_ids(reaction_message_id)
        if reaction_message_id not in messages_id:
            messages_id.append(reaction_message_id)
        print(messages_id)
        await delete_message(context, DEVELOPER_CHAT_ID, messages_id)
    if emoji == "😁":
        pass


def main() -> None:
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
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(MessageHandler(filters.Text(), echo))
    application.add_error_handler(error_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
