import re
import emoji
import json
import html
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
from typing import Any, cast
from core.database import *
from core.models import get_platform_logger
from core.settings import LOGS_DIR
from ops.process_posts import resolve_single_post
from urllib.parse import urlparse
from core.downloader import Downloader
from core.sender_dispatcher import execute_task
import warnings
from telegram.warnings import PTBUserWarning
from telegram import Bot

warnings.filterwarnings("ignore", category=PTBUserWarning)
logger = get_platform_logger('manage', LOGS_DIR)
headers = {
    'referer': 'https://www.baidu.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.183'
}
DEVELOPER_CHAT_ID = 708424141
MANAGE_BOT_TOKEN = os.getenv("ERROR_TELEGRAM_BOT_TOKEN", '')
logger.info("manage bot token is: " + MANAGE_BOT_TOKEN)
AVELEN_BOT_TOEKN = os.getenv("TELEGRAM_BOT_TOKEN", '')
logger.info("avelen bot token is: " + MANAGE_BOT_TOKEN, '')
SELECTING_PLATFORM, SELECTING_USER, MANAGING_USER = range(3)
ASK_SAVE_USERNAME, ASK_OPERATION, STORE_DATA = range(3)
POST_PROCESS_ACTION = range(1)
MARKDOWN_CHARS = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
follows = {}
follow_types = {
    '-2': '🚫 账号失效',
    '-1': '💔 不喜欢了',
    '0': ' ❗很久没更新',
    '1': '👤 普通关注',
    '2': '⭐️ 特别关注'
}
follow_type_icons = {
   '-2': '🚫 ',
    '-1': '💔  ',
    '0': ' ❗ ',
    '1': '👤  ',
    '2': '⭐️  '
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
    result = re.sub(r':\S+?:', '', result)
    # 只保留字母、数字、下划线，其余全部删除
    result = re.sub(r'\W', '', result)
    result = result.replace('_', r'\_')
    if result == '':
        return '没有名字'
    return result


def parse_url_platform(url):
    if 'douyin.com' in url:
        platform = 'douyin'
    elif 'weibo' in url:
        platform = 'weibo'
    elif 'instagram' in url:
        platform = 'instagram'
    elif 'bilibili' in url or url in ('b23.tv', 'bili2233.cn'):
        platform = 'bilibili'
    else:
        return None
    return platform


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
            (2, "⭐️ 特别关注", "upgrade"),
            (1, "👤 普通关注", "downgrade"),
            (0, "❗很久没更新", "delete"),
            (-1, "💔 不喜欢了", "retire"),
            (-2, "🚫 账号失效", "invalid"),
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
    if num == 1:
        user_id, username, latest_time, platform, valid = result[0]
        data = await query_user_info(user_id)
        await update.message.reply_text(data[1], reply_markup=InlineKeyboardMarkup(data[2]), parse_mode=ParseMode.HTML)
        return MANAGING_USER
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
    logger.info(data)
    action, user_id = data.split("|", 1)
    valid_map = {
        'upgrade': 2,
        'downgrade': 1,
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
    command = [BotCommand("manage", "管理关注"),
               BotCommand("cancel", "取消操作"),
               BotCommand("clear", "清理"),]
    await application.bot.set_my_commands(commands=command)
    await application.bot.send_message(DEVELOPER_CHAT_ID, text="bot start...")
    print("bot start ------------------->")


async def stop(application):
    await application.bot.send_message(DEVELOPER_CHAT_ID, "Shutting down...")
    print("bot stop ------------------->")


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
    logger.info(update.message.text)
    # TODO 提取出url后，先判断是用户主页地址还是post链接
    try:
        # 成功的话是post链接处理post
        resolve_result = resolve_single_post(url)
        if resolve_result.post is None:
            logger.info(f"{url} 获取数据失败，处理失败。")
            return ConversationHandler.END
        logger.info(resolve_result.post)
        downloader = Downloader(logger=logger)
        post_data = downloader.download(resolve_result.post)
        try:
            send_result = await execute_task(post_data)
        except Exception:
            await update.message.reply_text("发送失败")
            return ConversationHandler.END
        else:
            await update.message.reply_text("发送成功")
        return ConversationHandler.END
    except Exception as e:
        pass
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
    platform = parse_url_platform(host)
    if platform is None: return ConversationHandler.END

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
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"⭐️ 特别关注", callback_data="2")],
                                           [InlineKeyboardButton(f"👤 普通关注", callback_data="1")]])
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


async def delete_message(message_id):
    bot = Bot(token=AVELEN_BOT_TOEKN)
    logger.info(f"删除消息：{message_id}")
    try:
        if isinstance(message_id, list):
            await bot.delete_messages(DEVELOPER_CHAT_ID, message_id)
        else:
            await bot.delete_message(DEVELOPER_CHAT_ID, message_id)
        logger.info(f"删除消息成功")
    except Exception as exc:
        logger.error(f"删除消息失败")


def remove_downloaded_files(post_data):
    for root, dirs, files in os.walk(f"/root/download/{post_data['platform']}/"):
        for file in files:
            if file in post_data['files']:
                path = os.path.join(root, file)
                logger.info("删除文件：" + path)
                os.remove(path)


def _build_post_data_from_messages(messages: list[Any]) -> dict[str, Any] | None:
    if not messages:
        return None
    message_ids = [row[0] for row in messages]
    files = [row[1] for row in messages if row[1]]
    first = messages[0]
    return {
        'url': first[8],
        'idstr': first[11],
        'userid': first[9],
        'username': first[10],
        'messages_id': message_ids,
        'files': files,
        'platform': parse_url_platform(first[8])
    }


def _load_post_data(idstr: str, context: ContextTypes.DEFAULT_TYPE, *, force_refresh: bool = False) -> dict[
                                                                                                           str, Any] | None:
    post_cache = context.user_data.setdefault('post_cache', {})
    cached = None if force_refresh else post_cache.get(idstr)
    if cached:
        return cached
    messages = exec_sql_get_data('select * from messages where idstr=%s', (idstr,))
    post_data = _build_post_data_from_messages(messages)
    if post_data:
        post_cache[idstr] = post_data
    return post_data


async def handle_forwarded_post_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        return ConversationHandler.END
    message = update.message
    if not message:
        return ConversationHandler.END
    forward_origin = message.forward_origin
    if not forward_origin or getattr(forward_origin, "sender_user", None) is None:
        return ConversationHandler.END
    if forward_origin.sender_user.id != 6572044525:
        return ConversationHandler.END
    if message.text:
        post_idstr = message.text.split("  ")[1].split("\n")[0]
        messages = exec_sql_get_data('select * from messages where idstr=%s', (post_idstr,))
    elif message.caption:
        messages = exec_sql_get_data(
            "select * from messages where idstr in (select idstr from messages where caption=%s)", (message.caption))
    else:
        return ConversationHandler.END
    post_data = _build_post_data_from_messages(messages)
    if not post_data:
        await update.message.reply_text("未查到对应作品记录")
        return ConversationHandler.END
    context.user_data.setdefault('post_cache', {})[post_data['idstr']] = post_data
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("删除", callback_data=f"post|delete|{post_data['idstr']}"),
        InlineKeyboardButton("重发", callback_data=f"post|resend|{post_data['idstr']}"),
        InlineKeyboardButton("清理", callback_data=f"post|clear|{post_data['idstr']}")
    ]])
    text = (
        f"提取到作品信息：\n"
        f"<pre>{html.escape(json.dumps(post_data, indent=2, ensure_ascii=False))}</pre>"
    )
    await update.message.reply_text(text=text, reply_to_message_id=message.id, reply_markup=keyboard,
                                    parse_mode=ParseMode.HTML)
    return POST_PROCESS_ACTION


async def handle_post_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        await query.edit_message_text("你没有权限执行该操作")
        return ConversationHandler.END

    data = cast(str, query.data)
    parts = data.split("|")
    if len(parts) < 3:
        await query.edit_message_text("❌ 无效操作")
        return ConversationHandler.END

    prefix, action, idstr = parts[:3]
    post_data = _load_post_data(idstr, context)

    if post_data is None:
        await query.edit_message_text(f"❌ 未找到作品记录: {idstr}")
        return ConversationHandler.END

    if action == 'delete':
        logger.info(f'删除 {post_data['url']} 的已发送消息')
        result = await delete_message(post_data['messages_id'])
        context.user_data.get('post_cache', {}).pop(idstr, None)
        await query.edit_message_text(
            "✅ 删除完成\n"
            f"idstr: {idstr}\n"
            f"url: {post_data['url']}\n"
        )
        return ConversationHandler.END
    elif action == 'clear':
        logger.info("清理 {} 的重复发送内容".format(post_data['url']))
        duplicate = get_duplicate_caption(post_data['url'])
        if len(duplicate) > 0:
            print(f"共有{len(duplicate)}个记录")
            for url, caption in duplicate:
                message_ids = get_message_id(caption, url)
                if len(message_ids) > 0:
                    delete_messages = message_ids[0:-1]
                    logger.info(f"消息内容：{caption}, 所有消息：{message_ids}, 待删除的消息：{delete_messages}")
                    await delete_message(delete_messages)
                    delete_db_message(delete_messages)
        logger.info("清理 {} 的重复发送内容完成".format(post_data['url']))
    if action == 'resend':
        result = await delete_message(post_data['messages_id'])
        remove_downloaded_files(post_data)
        resolve_result = resolve_single_post(post_data['url'])
        if resolve_result.post is None:
            await query.edit_message_text(
                "❌ 重发失败\n"
                f"idstr: {idstr}\n"
                f"url: {post_data['url']}\n"
                f"api_error: {resolve_result.api_error or '未知'}\n"
                f"local_error: {resolve_result.local_error or '未知'}"
            )
            return ConversationHandler.END
        downloader = Downloader(logger=logger)
        post_data = downloader.download(resolve_result.post)
        try:
            send_result = await execute_task(post_data)
        except Exception:
            await query.edit_message_text("发送失败")
            return ConversationHandler.END
        else:
            await query.edit_message_text("发送成功")
        refreshed_post_data = _load_post_data(idstr, context, force_refresh=True)
        if refreshed_post_data:
            refreshed_post_data['messages_id'] = list(dict.fromkeys(refreshed_post_data['messages_id']))
            refreshed_post_data['files'] = list(dict.fromkeys(refreshed_post_data['files']))
        await query.edit_message_text("✅ 重发完成\n")
        return ConversationHandler.END

    await query.edit_message_text("❌ 未知操作")
    return ConversationHandler.END


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != DEVELOPER_CHAT_ID:
        return None
    message_id = update.message.message_id
    duplicate = get_duplicate_messages()
    total = len(duplicate)
    index = 0
    if total > 0:
        logger.info(f"共有{total}个记录")
        await update.message.reply_text(text=f"共有{total}个记录")
        for url, caption in duplicate:
            index += 1
            message_ids = get_message_id(caption, url)
            if len(message_ids) >= 2:
                delete_messages = message_ids[0:-1]
                logger.info(f'{index}/{total}  {url}  {caption}  {message_ids}  {delete_messages}')
                logger.info(f"删除数据库数据，message_id: {delete_messages}")
                delete_db_message(delete_messages)
                await delete_message(delete_messages)


def main() -> None:
    builder = Application.builder()
    persistence = PicklePersistence(filepath="arbitrarycallbackdatabot")
    builder.token(MANAGE_BOT_TOKEN)
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
    add_follower_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'(https?://[^\s]+)'), handle_url)],
        states={
            ASK_SAVE_USERNAME: [
                MessageHandler(filters.Regex(r'(https?://[^\s]+)'), handle_url),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_save_username)
            ],
            STORE_DATA: [
                MessageHandler(filters.Regex(r'(https?://[^\s]+)'), handle_url),
                CallbackQueryHandler(store_data, pattern=r"[0|1|2]"),
                CallbackQueryHandler(update_user_valid, pattern=r"^(delete|upgrade|downgrade|retire|invalid)\|")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    post_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.FORWARDED, handle_forwarded_post_message)],
        states={
            POST_PROCESS_ACTION: [
                MessageHandler(filters.FORWARDED, handle_forwarded_post_message),
                CallbackQueryHandler(handle_post_action, pattern=r"^post\|")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(add_follower_handler)
    application.add_handler(post_handler)
    application.add_handler(manage_follow_handler)
    application.add_handler(CommandHandler("clear", clear))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
