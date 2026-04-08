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
from core.database import exec_sql_get_data, add_user, update_user
from urllib.parse import urlparse
from ops.nicefuturebot import delete_message

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
    '-2': '🚫 无效账号',
    '-1': '🗂️ 不再追踪',
    '0': '❌ 取消追踪',
    '1': '⭐️ 特别关注',
    '2': '👤 普通关注'
}
follow_type_icons = {
    '-2': '🚫',
    '-1': '🗂️',
    '0': '❌',
    '1': '⭐️',
    '2': '👤'
}
platform_icons = {
    'douyin': '🎵',
    'weibo': '📣',
    'instagram': '📸',
    'bilibili': '📺',
}
PAGE_SIZE = 30
MANAGE_PLATFORMS = ['douyin', 'weibo', 'instagram', 'bilibili']


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
    """
    当输入 /manage 命令时会进入这个函数，返回平台按钮，点击后进入 query_data 查找数据
    """
    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        await update.message.reply_text("你没有权限使用此命令")
        return ConversationHandler.END
    keyboard = []
    row = []
    for platform in MANAGE_PLATFORMS:
        btn = InlineKeyboardButton(f"{platform_icons[platform]} {platform}", callback_data=f"s|{platform}|1")
        row.append(btn)
    keyboard.append(row)
    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text("选择一个平台:", reply_markup=markup)
    else:
        await update.message.reply_text("选择一个平台:", reply_markup=markup)
    return SELECTING_PLATFORM


async def query_user_info(user_id):
    exist = exec_sql_get_data("select * from user where userid=%s", (user_id,))
    if exist:
        user_id, username, latest_time, platform, scrapy_time, valid = exist[0]
        if platform == 'douyin':
            keyboard_button = InlineKeyboardButton("📎 在抖音上查看", url=f"https://www.douyin.com/user/{user_id}")
        elif platform == 'weibo':
            keyboard_button = InlineKeyboardButton("📎 在微博上查看", url=f"https://weibo.com/u/{user_id}")
        elif platform == 'bilibili':
            keyboard_button = InlineKeyboardButton("📎 在B站上查看", url=f"https://space.bilibili.com/{user_id}")
        else:
            keyboard_button = InlineKeyboardButton("📎 在Instagram上查看",
                                                   url=f"https://www.instagram.com/{user_id}/")

        keyboard = [[keyboard_button]]
        status_actions = [
            (1, "⭐️ 特别关注", "upgrade"),
            (2, "👤 普通关注", "downgrade"),
            (0, "❌ 取消关注", "delete"),
            (-1, "🗂️ 不再追踪", "retire"),
            (-2, "🚫 无效账号", "invalid"),
        ]
        upgrade_button = []
        for target_valid, text, action in status_actions:
            if valid != target_valid:
                upgrade_button.append(InlineKeyboardButton(text, callback_data=f"{action}|{user_id}"))
                if len(upgrade_button) == 2:
                    keyboard.append(upgrade_button)
                    upgrade_button = []
        sql = """SELECT u.USERNAME,
                        u.USERID,
                        u.platform,
                        COUNT(DISTINCT m.IDSTR) AS num
                 FROM user u
                          LEFT JOIN messages m ON u.USERID = m.USERID
                 WHERE u.USERID = %s
                 GROUP BY u.USERID"""
        result = exec_sql_get_data(sql, (user_id,))
        if result:
            user_name, num = result[0][0], result[0][-1]
        else:
            user_name, num = user_id, 0
        info = f"<b>#{user_name}</b>\n<b>用户ID</b>：{user_id}\n<b>平台</b>：{platform}\n<b>最新作品</b>：{str(latest_time or '')}\n<b>作品数量：</b>{num}\n<b>关注类型：</b>{follow_types.get(str(valid), f'未知类型({valid})')}"
        return exist[0], info, keyboard
    return None


async def query_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    输入任意字符进入此函数，也可以通过 callback_query 进入（为：^s\|）。通过关键字查找所有的用户并分页展示出来
    """
    query = update.callback_query
    if query:
        platform_icons_enable = False
        # 通过 callback_query , 数据形如 s/{search_text}/{page}
        await query.answer()
        _, search_text, page = query.data.split("|", 2)
        page = int(page)
        context.user_data['search_text'] = search_text
        await context.bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.TYPING)
    else:
        platform_icons_enable = True
        # 通过输入任意字符串进入，然后使用字符串查找数据
        if update.effective_chat.id != DEVELOPER_CHAT_ID:
            return ConversationHandler.END
        search_text = update.message.text
        page = 1
    context.user_data['page'] = page
    try:
        valid_type = int(search_text)
    except ValueError:
        valid_type = None
    if valid_type in (-2, -1, 0, 1, 2):
        sql = """SELECT userid, username, latest_time, platform, valid
                 FROM user
                 WHERE valid = %s"""
        result = exec_sql_get_data(sql, (valid_type,))
    else:
        sql = """SELECT userid, username, latest_time, platform, valid
                 FROM user
                 WHERE userid LIKE %s
                    OR username LIKE %s
                    OR platform = %s"""
        result = exec_sql_get_data(sql, (f"%{search_text}%", f"%{search_text}%", search_text,))
    result = list(sorted(result, key=lambda x: x[2], reverse=True))
    num = len(result)
    if num == 0:
        if query:
            await query.edit_message_text("无结果")
        else:
            await update.message.reply_text("无结果")
        return ConversationHandler.END
    total_pages = num // PAGE_SIZE + 1
    keyboard = []
    row = []
    start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
    for user in result[start:end]:
        user_id, username, latest_time, platform, valid = user
        icon = follow_type_icons.get(str(valid), '❓')
        platform_icon = platform_icons.get(platform, '❓')
        if platform_icons_enable:
            username_remark = f'{icon} {platform_icon} {username}'
        else:
            username_remark = f'{icon} {username}'
        follows[user_id] = {
            'username': username,
            'latest_time': latest_time,
            'platform': platform,
            'valid': valid
        }
        btn = InlineKeyboardButton(f"{username_remark}", callback_data=f"user|{search_text}|{user_id}")
        row.append(btn)
        if len(row) == 3:
            keyboard.append(row)
            row = []
    keyboard.append(row)
    keyboard.append([InlineKeyboardButton(f"返回选择平台", callback_data=f"back|platform")])
    if num > PAGE_SIZE:
        if page == 1:
            keyboard.append([InlineKeyboardButton(f"下一页", callback_data=f"s|{search_text}|{page + 1}"),
                             InlineKeyboardButton(f"最后一页", callback_data=f"s|{search_text}|{total_pages}")])
        elif page == total_pages:
            keyboard.append([InlineKeyboardButton(f"第一页", callback_data=f"s|{search_text}|{1}"),
                             InlineKeyboardButton(f"上一页", callback_data=f"s|{search_text}|{total_pages - 1}")])
        elif page + 1 == total_pages:
            keyboard.append([InlineKeyboardButton(f"上一页", callback_data=f"s|{search_text}|{page - 1}"),
                             InlineKeyboardButton(f"最后一页", callback_data=f"s|{search_text}|{total_pages}")])
        else:
            keyboard.append([InlineKeyboardButton(f"上一页", callback_data=f"s|{search_text}|{page - 1}"),
                             InlineKeyboardButton(f"下一页", callback_data=f"s|{search_text}|{page + 1}"),
                             InlineKeyboardButton(f"最后一页", callback_data=f"s|{search_text}|{total_pages}")])
    markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(
            f"有{num}个用户，当前显示第{start + 1}个到第{min(end, num)}个。点击管理一个用户:",
            reply_markup=markup)
    else:
        await update.message.reply_text(f"有{num}个用户，当前显示第{start + 1}个到第{min(end, num)}个。点击管理一个用户:",
                                        reply_markup=markup)
    return SELECTING_USER


async def handle_user_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理 query_data 中选择的数据，展示当前用户的详细数据
    """
    query = update.callback_query
    await query.answer()
    data = cast(str, query.data)
    _, search_text, user_id = data.split("|", 2)
    page = context.user_data.get('page', 1)
    await context.bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.TYPING)
    data = await query_user_info(user_id)
    data[2].append([InlineKeyboardButton("⬅️ 返回用户列表", callback_data=f"back|{search_text}|{page}")])
    await query.edit_message_text(data[1], reply_markup=InlineKeyboardMarkup(data[2]), parse_mode=ParseMode.HTML)
    return MANAGING_USER


async def update_user_valid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = cast(str, query.data)
    action, user_id = data.split("|", 1)
    valid_map = {
        'upgrade': 1,
        'downgrade': 2,
        'delete': 0,
        'retire': -1,
        'invalid': -2
    }
    valid = valid_map.get(action)
    if valid is None:
        await query.edit_message_text("❌ 未知操作")
        return ConversationHandler.END
    update_user(valid, user_id)
    data = await query_user_info(user_id)
    await query.edit_message_text(f"修改成功\n" + data[1], reply_markup=InlineKeyboardMarkup([data[2][0]]),
                                  parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# === Back button ===
async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = cast(str, query.data)
    if data == 'back|platform':
        return await start_manage(update, context)
    else:
        return await query_data(update, context)


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
        result = exec_sql_get_data("select username from statistic order by num desc")
        text = ''
        for username in result:
            username = clear_name(username)
            text += f'\#{username}   '
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


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

    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        await update.message.reply_text("你没有权限使用此命令")
        return ConversationHandler.END

    matches = re.compile(r"(https?://[^\s]+)").findall(update.message.text.strip())
    url = matches[0]
    short_domains = ('v.douyin.com', 'b23.tv', 'bili2233.cn')
    if any(domain in url for domain in short_domains) or '哔哩哔哩' in url:
        url = extract_url(url)
        print(url)
        if not url:
            await update.message.reply_text("未提取到用户主页地址，请重新开始。")
            return ConversationHandler.END
        url = expand_url(url)
        print(url)
    if url[-1] == '/':
        url = url[:-1]
    context.user_data["url"] = url.split('?')[0]
    parsed_url = urlparse(url)
    host = parsed_url.hostname or ''
    if 'douyin.com' in host:
        platform = 'douyin'
    elif 'weibo' in host:
        platform = 'weibo'
    elif 'instagram' in host:
        platform = 'instagram'
    elif 'bilibili' in host or host in ('b23.tv', 'bili2233.cn'):
        platform = 'bilibili'
    else:
        await update.message.reply_text("未知的平台")
        return ConversationHandler.END
    url_path = parsed_url.path.rstrip('/')
    segments = [item for item in url_path.split('/') if item]
    if platform == 'bilibili' and len(segments) >= 1 and segments[0].isdigit():
        user_id = segments[0]
    elif segments:
        user_id = segments[-1]
    else:
        user_id = ''

    if not user_id:
        await update.message.reply_text("❌ 无法提取到用户id")
        return ConversationHandler.END

    context.user_data["user_id"] = user_id
    context.user_data["platform"] = platform
    await context.bot.send_chat_action(DEVELOPER_CHAT_ID, ChatAction.TYPING)
    data = await query_user_info(user_id)
    if data:
        context.user_data["type"] = 'old'
        context.user_data['username'] = data[0][1]
        await update.message.reply_text(data[1], parse_mode="HTML", reply_markup=InlineKeyboardMarkup(data[2]))
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
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"⭐️ 特别关注", callback_data="1")],
                                           [InlineKeyboardButton(f"👤 普通关注", callback_data="2")]])
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
    return ConversationHandler.END


def main() -> None:
    weibo_filter = filters.Regex('^https://(m.|www.)?weibo(.cn|.com)?/[0-9]+/*')
    douyin_filter = filters.Regex('https://(v.|www.|live.)?(ies)?douyin.*')
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
        entry_points=[CommandHandler("manage", start_manage),
                      MessageHandler(filters.Text() & ~filters.COMMAND, query_data)],
        states={
            SELECTING_PLATFORM: [
                CommandHandler("manage", start_manage),
                MessageHandler(filters.Text() & ~filters.COMMAND, query_data),
                CallbackQueryHandler(query_data, pattern=r"^s\|")
            ],
            SELECTING_USER: [
                CommandHandler("manage", start_manage),
                MessageHandler(filters.Text() & ~filters.COMMAND, query_data),
                CallbackQueryHandler(query_data, pattern=r"^s\|"),
                CallbackQueryHandler(handle_user_selected, pattern=r"^user\|"),
                CallbackQueryHandler(handle_back, pattern=r"^back\|")
            ],
            MANAGING_USER: [
                CommandHandler("manage", start_manage),
                MessageHandler(filters.Text() & ~filters.COMMAND, query_data),
                CallbackQueryHandler(update_user_valid, pattern=r"^(delete|upgrade|downgrade|retire|invalid)\|"),
                CallbackQueryHandler(handle_back, pattern=r"^back\|")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    add_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('(https?://[^\s]+)'), handle_url)],
        states={
            ASK_SAVE_USERNAME: [
                MessageHandler(filters.Regex('(https?://[^\s]+)'), handle_url),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_save_username)
            ],
            STORE_DATA: [
                MessageHandler(filters.Regex('(https?://[^\s]+)'), handle_url),
                CallbackQueryHandler(store_data, pattern=r"[0|1|2]"),
                CallbackQueryHandler(update_user_valid, pattern=r"^(delete|upgrade|downgrade|retire|invalid)\|")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_handler)
    application.add_handler(CommandHandler("lm", ls_media))
    application.add_handler(CommandHandler("myfollow", list_my_follow))
    application.add_handler(manage_follow_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
