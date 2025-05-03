from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    PicklePersistence,
)
from telegram.constants import ParseMode
from typing import cast
from database import exec_sql_get_data
import subprocess

DEVELOPER_CHAT_ID = 708424141
SELECTING_PLATFORM, SELECTING_USER, MANAGING_USER = range(3)
follows = {}


async def start_manage(update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    row = []
    for platform in ['douyin', 'weibo', 'instagram']:
        btn = InlineKeyboardButton(f"{platform}", callback_data=f"platform|{platform}")
        row.append(btn)
    keyboard.append(row)
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text("选择一个平台:", reply_markup=markup)
    else:
        await update.message.reply_text("选择一个平台:", reply_markup=markup)
    return SELECTING_PLATFORM


async def handle_platform_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, platform = query.data.split("|", 1)
    context.user_data['platform'] = platform
    result = exec_sql_get_data(f"select * from user where platform='{platform}'")
    result = list(sorted(result, key=lambda x: x[2], reverse=True))
    num = len(result)
    keyboard = []
    row = []
    for user in result:
        user_id, username, latest_time, platform, scrapy_time = user
        follows[user_id] = {
            'username': username,
            'latest_time': latest_time,
            'platform': platform,
            'scrapy_time': scrapy_time
        }
        btn = InlineKeyboardButton(f"{username}", callback_data=f"user|{user_id}")
        row.append(btn)
        if len(row) == 3:
            keyboard.append(row)
            row = []
    keyboard.append(row)
    keyboard.append([InlineKeyboardButton(f"返回选择平台", callback_data=f"back|myfollow")])
    markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(f"有{num}个用户，选择管理一个用户:", reply_markup=markup)

    return SELECTING_USER


async def handle_user_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = cast(str, query.data)
    _, user_id = data.split("|", 1)
    user_name = follows[user_id]['username']
    context.user_data["selected_username"] = user_id
    platform = follows[user_id]['platform']
    if platform == 'douyin':
        keyboard_button = InlineKeyboardButton("📎 View on Douyin", url=f"https://www.douyin.com/user/{user_id}")
    elif platform == 'weibo':
        keyboard_button = InlineKeyboardButton("📎 View on Weibo", url=f"https://weibo.com/u/{user_id}")
    else:
        keyboard_button = InlineKeyboardButton("📎 View on Instagram",
                                               url=f"https://www.instagram.com/{follows[user_id]['username']}/")
    keyboard = [
        [keyboard_button],
        [InlineKeyboardButton("❌ 删除", callback_data="delete")],
        [InlineKeyboardButton("⬅️ 返回用户列表", callback_data=f"back|{platform}")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    result = exec_sql_get_data(f"select num from statistic where userid='{user_id}'")
    num = result[0]
    await query.edit_message_text(
        f"<b>{user_name}</b>\n<b>最新作品</b>：{str(follows[user_id]['latest_time'])}\n<b>作品数量：</b>{num}",
        reply_markup=markup, parse_mode=ParseMode.HTML)
    return MANAGING_USER


# === Delete user ===
async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    username = context.user_data.get("selected_username")
    user_id = query.from_user.id
    print(user_id, username)
    await query.edit_message_text(f"✅ Unfollowed @{username}")
    return ConversationHandler.END


# === Back button ===
async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = cast(str, query.data)
    if data == 'back|myfollow':
        return await start_manage(update, context)
    else:
        return await handle_platform_selected(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text(
        "Bye! You can redo anytime!!!"
    )
    return ConversationHandler.END


async def edit_commands(application):
    command = [BotCommand("myfollow", "管理关注"),
               BotCommand("lm", "查看/media文件夹")]
    await application.bot.set_my_commands(commands=command)
    print("bot start ------------------->")


async def stop(application):
    await application.bot.send_message(DEVELOPER_CHAT_ID, "Shutting down...")
    print("bot stop ------------------->")


async def ls_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == DEVELOPER_CHAT_ID:
        result = subprocess.run('ls -lth /media', shell=True, capture_output=True, text=True)
        msg = ''
        for i, line in enumerate(result.stdout.splitlines()):
            if i == 0:
                text = line
            else:
                text = ' '.join(line.split()[4:])
            msg = msg + text + '\n'
        await update.message.reply_text(msg)
        return


def main() -> None:
    builder = Application.builder()
    persistence = PicklePersistence(filepath="arbitrarycallbackdatabot")
    builder.token('5355419947:AAEHOGlkz7hlOO38XRRZ9vVhtAnVGjwbjKw')
    builder.post_init(edit_commands)
    builder.post_stop(stop)
    builder.http_version('1.1')
    builder.get_updates_http_version('1.1')
    builder.base_url(r'http://localhost:8081/bot')
    builder.base_file_url(r'http://localhost:8081/file/bot')
    builder.local_mode(local_mode=True)
    builder.persistence(persistence)
    builder.arbitrary_callback_data(True)
    application = builder.build()

    manage_follow_handler = ConversationHandler(
        entry_points=[CommandHandler("myfollow", start_manage)],
        states={
            SELECTING_PLATFORM: [
                CallbackQueryHandler(handle_platform_selected, pattern=r"^platform\|")
            ],
            SELECTING_USER: [
                CallbackQueryHandler(handle_user_selected, pattern=r"^user\|"),
                CallbackQueryHandler(handle_back, pattern=r"^back\|")
            ],
            MANAGING_USER: [
                CallbackQueryHandler(handle_delete, pattern=r"^delete\|"),
                CallbackQueryHandler(handle_back, pattern=r"^back\|")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(CommandHandler("lm", ls_media))
    application.add_handler(manage_follow_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
