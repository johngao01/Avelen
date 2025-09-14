import re
import subprocess
import emoji
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    PicklePersistence,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode, ChatAction
from typing import cast
from database import exec_sql_get_data, add_user, update_user
from urllib.parse import urlparse

headers = {
    'referer': 'https://www.baidu.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.183'
}
DEVELOPER_CHAT_ID = 708424141
SELECTING_PLATFORM, SELECTING_USER, MANAGING_USER = range(3)
ASK_SAVE_USERNAME, ASK_OPERATION, STORE_DATA = range(3)
MARKDOWN_CHARS = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
follows = {}
follow_types = {
    '0': '删除',
    '1': '特别关注',
    '2': '普通关注'
}

bottoms = [
    InlineKeyboardButton(f"删除", callback_data="0"),
    InlineKeyboardButton(f"特别关注", callback_data="1"),
    InlineKeyboardButton(f"普通关注", callback_data="2")
]


def clear_name(text):
    # 去除中英文小括号及其内容
    result = re.sub(r'[（(【].*?[】)）]', '', text)
    # 去除表情
    result = emoji.demojize(result)
    result = re.sub(':\S+?:', '', result)
    # 只保留字母、数字、下划线，其余全部删除
    result = re.sub(r'[^\w]', '', result)
    result = result.replace('_', r'\_')
    if result == '':
        return '没有名字'
    return result


async def start_manage(update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        await update.message.reply_text("你没有权限使用此命令")
        return ConversationHandler.END
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
    await context.bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.TYPING)
    result = exec_sql_get_data(
        f"select userid, username, latest_time, platform, valid from user where platform='{platform}' and valid>0")
    result = list(sorted(result, key=lambda x: x[2], reverse=True))
    num = len(result)
    keyboard = []
    row = []
    for user in result:
        user_id, username, latest_time, platform, valid = user
        follows[user_id] = {
            'username': username,
            'latest_time': latest_time,
            'platform': platform,
            'valid': valid
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
    context.user_data["selected_username"] = user_name
    platform = follows[user_id]['platform']
    if platform == 'douyin':
        keyboard_button = InlineKeyboardButton("📎 在抖音上查看", url=f"https://www.douyin.com/user/{user_id}")
    elif platform == 'weibo':
        keyboard_button = InlineKeyboardButton("📎 在微博上查看", url=f"https://weibo.com/u/{user_id}")
    else:
        keyboard_button = InlineKeyboardButton("📎 在Instagram上查看",
                                               url=f"https://www.instagram.com/{follows[user_id]['username']}/")
    if follows[user_id]['valid'] == 1:
        update_button = InlineKeyboardButton("👤 普通关注", callback_data=f"downgrade|{user_id}")
    else:
        update_button = InlineKeyboardButton("⭐️ 特别关注", callback_data=f"upgrade|{user_id}")
    keyboard = [
        [keyboard_button],
        [InlineKeyboardButton("❌ 取消关注", callback_data=f"delete|{user_id}")],
        [update_button],
        [InlineKeyboardButton("⬅️ 返回用户列表", callback_data=f"back|{platform}")]
    ]

    markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.TYPING)
    result = exec_sql_get_data(f"select num from statistic where userid='{user_id}'")
    num = result[0]
    await query.edit_message_text(
        f"<b>#{user_name}</b>\n<b>最新作品</b>：{str(follows[user_id]['latest_time'])}\n"
        f"<b>作品数量：</b>{num}\n<b>关注类型：</b>{follow_types[str(follows[user_id]['valid'])]}",
        reply_markup=markup, parse_mode=ParseMode.HTML)
    return MANAGING_USER


async def update_user_valid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = cast(str, query.data)
    _, user_id = data.split("|", 1)
    username = context.user_data.get("selected_username")
    print(user_id, username, _)
    if _ == 'upgrade':
        valid = 1
    elif _ == 'downgrade':
        valid = 2
    else:
        valid = 0
    update_user(valid, user_id)
    await query.edit_message_text(f"✅ Unfollowed #{username}")
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
        "再见!!!"
    )
    return ConversationHandler.END


async def edit_commands(application):
    command = [BotCommand("myfollow", "我的关注"),
               BotCommand("manage", "管理关注"),
               BotCommand("lm", "查看/media文件夹"),
               BotCommand("cancel", "取消操作")]
    await application.bot.set_my_commands(commands=command)
    await application.bot.send_message(DEVELOPER_CHAT_ID,
                                       text="bot start...")
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


async def list_my_follow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == DEVELOPER_CHAT_ID:
        await context.bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.TYPING)
        result = exec_sql_get_data(f"select username from statistic order by num desc")
        text = ''
        for username in result:
            username = clear_name(username)
            text += f'\#{username}   '
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(update.effective_user.language_code, update.message.chat_id, update.message.id, update.message.date,
          update.message.text)
    await update.message.reply_text(update.message.text)


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    def expand_url(short_url: str) -> str:
        try:
            response = requests.get(short_url, timeout=5, allow_redirects=True, headers=headers)
            return response.url
        except requests.RequestException as e:
            print(f"获取真实地址失败: {e}")
            return short_url

    def extract_url(text: str) -> str | None:
        # 提取第一个 http(s) 开头的 URL
        match = re.search(r'(https?://[^\s]+)', text)
        return match.group(0) if match else None

    matches = re.compile(r"(https?://[^\s]+)").findall(update.message.text.strip())

    url = matches[0]
    if 'v.doyin.com' in url:
        url = extract_url(url)
        print(url)
        if not url:
            await update.message.reply_text("未提取到用户主页地址，请重新开始。")
            return ConversationHandler.END
        url = expand_url(url)
        print(url)
    context.user_data["url"] = url
    parsed_url = urlparse(url)
    if 'douyin.com' in parsed_url.hostname:
        platform = 'douyin'
    elif 'weibo' in parsed_url.hostname:
        platform = 'weibo'
    elif 'instagram' in parsed_url.hostname:
        platform = 'instagram'
    else:
        await update.message.reply_text("未知的平台")
        return ConversationHandler.END
    url_path = parsed_url.path
    user_id = url_path.split('/')[-1]

    if not user_id:
        await update.message.reply_text("❌ 无法提取到用户id")
        return ConversationHandler.END

    context.user_data["user_id"] = user_id
    context.user_data["platform"] = platform
    exist = exec_sql_get_data(f"select * from user where userid='{user_id}'")

    if exist:
        context.user_data["type"] = 'old'
        user_id, username, latest_time, platform, scrapy_time, valid = exist[0]
        if valid == 1:
            reply_bottoms = [bottoms[0], bottoms[2]]
        elif valid == 2:
            reply_bottoms = [bottoms[0], bottoms[1]]
        else:
            reply_bottoms = [bottoms[1], bottoms[2]]
        await context.bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.TYPING)
        result = exec_sql_get_data(f"select * from statistic where userid='{user_id}'")
        user_name, num = result[0][0], result[0][-1]
        await update.message.reply_text(
            f"<b>#{user_name}</b>\n<b>最新作品</b>：{str(latest_time or '')}\n"
            f"<b>作品数量：</b>{num}\n<b>关注类型：</b>{follow_types[str(valid)]}\n选择关注类型", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([reply_bottoms])
        )
        return STORE_DATA
    else:
        context.user_data["type"] = 'new'
        await update.message.reply_text(
            f"😀 新关注 输入用户名 或者 /cancel 取消操作"
        )
        return ASK_SAVE_USERNAME


async def ask_save_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["username"] = update.message.text
    await update.message.reply_text(
        f"选择关注类型",
        reply_markup=InlineKeyboardMarkup([bottoms[1:]])
    )
    return STORE_DATA


async def store_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.TYPING)
    url = context.user_data["url"]
    user_id = context.user_data["user_id"]
    platform = context.user_data["platform"]
    username = context.user_data["username"]
    query = update.callback_query
    await query.answer()
    valid = cast(str, query.data)
    if context.user_data["type"] == 'new':
        add_user(user_id, username, platform, valid)
        await query.edit_message_text(f"✅ 新增 {follow_types[str(valid)]} [{username}]({url}) 成功",
                                      parse_mode=ParseMode.MARKDOWN_V2)
    else:
        update_user(valid, user_id)
        if valid == '0':
            await query.edit_message_text(f"✅ 取消关注 [{username}]({url}) 成功", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await query.edit_message_text(f"✅ 修改 [{username}]({url}) 为 {follow_types[str(valid)]} 成功",
                                          parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END


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
        entry_points=[CommandHandler("manage", start_manage)],
        states={
            SELECTING_PLATFORM: [
                CommandHandler("manage", start_manage),
                CallbackQueryHandler(handle_platform_selected, pattern=r"^platform\|")
            ],
            SELECTING_USER: [
                CommandHandler("manage", start_manage),
                CallbackQueryHandler(handle_user_selected, pattern=r"^user\|"),
                CallbackQueryHandler(handle_back, pattern=r"^back\|")
            ],
            MANAGING_USER: [
                CommandHandler("manage", start_manage),
                CallbackQueryHandler(update_user_valid, pattern=r"^[delete|upgrade|downgrade]\|"),
                CallbackQueryHandler(handle_back, pattern=r"^back\|")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    add_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('(https?://[^\s]+)'), handle_url)],
        states={
            ASK_SAVE_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_save_username)
            ],
            STORE_DATA: [
                CallbackQueryHandler(store_data, pattern=r"[0|1|2]")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_handler)
    application.add_handler(CommandHandler("lm", ls_media))
    application.add_handler(CommandHandler("myfollow", list_my_follow))
    application.add_handler(manage_follow_handler)
    application.add_handler(MessageHandler(filters.Text(), echo))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
