# weibo-tg-bot

一个面向个人使用的多平台内容抓取与 Telegram 分发项目。

项目当前支持抓取以下平台的新内容：

- 微博
- 抖音
- Instagram
- Bilibili

抓取到的内容会被统一解析、下载到本地，然后通过 Telegram Bot 发送给指定聊天，并把发送结果写入 MySQL，避免重复发送。

## 项目目标

这个项目主要解决一件事：

1. 从多个平台轮询关注对象的新内容
2. 把不同平台的数据统一成同一种内部结构
3. 下载图片 / 视频等媒体到本地
4. 通过 Telegram Bot 发送媒体和文本
5. 记录发送结果，便于去重、补发和后续管理

## 当前目录结构

```text
weibo_tg_bot/
  main.py

  platforms/
    weibo.py
    douyin.py
    instagram.py
    bilibili.py

  core/
    platform.py
    post.py
    downloader.py
    sender_dispatcher.py
    scrapy_runner.py
    following.py
    database.py
    settings.py
    utils.py
    package.py
    pipeline.py

  ops/
    manage.py
    nicefuturebot.py
    deal_error.py
    chat_download.py
    modify_msg.py
    modify_msg_legacy.py

  cookies/
  logs/
  .env.example
  pyproject.toml
```

### 目录职责

- `main.py`
  - 统一入口
  - 根据平台名选择对应的 `Platform` 类并运行

- `platforms/`
  - 每个平台只有一个脚本
  - 同时包含抓取、解析、下载协调、发送入口
  - 暴露统一的 `Platform` 类给根目录入口注册

- `core/`
  - 平台共用的核心能力
  - 包括平台基类、数据模型、下载器、发送分发、数据库、运行参数等

- `ops/`
  - 非主抓取链路的运维/辅助脚本
  - 比如管理用户、补发错误、下载历史媒体、批量修改消息

## 核心工作流

主流程大致如下：

```text
main.py
  -> platforms registry
    -> selected Platform class
      -> platforms/<platform>.py
    -> 读取 user 表中的关注对象
    -> 抓取平台内容
    -> 转成 BasePost / MediaItem
    -> Downloader 下载媒体
    -> sender_dispatcher 发送到 Telegram
    -> messages 表写入发送记录
    -> user 表更新 latest_time / scrapy_time
```

### 关键模块

- `core/post.py`
  - 定义统一内容结构
  - `BasePost`：平台内容基类
  - `MediaItem`：待下载媒体描述

- `core/platform.py`
  - 定义统一平台入口基类
  - 每个平台通过 `Platform.run(argv)` 暴露启动能力

- `core/downloader.py`
  - 统一下载入口
  - 负责重试、Session 复用、落地文件、媒体分类

- `core/sender_dispatcher.py`
  - 统一 Telegram 发送
  - 串行发送，避免多个抓取任务互相打乱
  - 发送后立即写数据库

- `core/database.py`
  - MySQL 读写
  - 查询关注对象、去重 URL、更新抓取时间、管理用户

- `core/scrapy_runner.py`
  - 平台通用 CLI 参数
  - 平台通用“遍历关注对象并执行”的入口

## 支持的平台脚本

根目录 `main.py` 不再通过 `runpy` 按模块字符串跳转，而是先根据平台名从注册表中选择对应的平台类，再把剩余 CLI 参数透传给该类。

### `platforms/weibo.py`

负责：

- 微博关注对象模型
- 微博接口抓取
- 单条微博解析
- 图片 / livephoto / 视频下载与分发

适用命令：

```bash
python main.py weibo
```

### `platforms/douyin.py`

负责：

- 抖音关注对象模型
- 抖音作品列表抓取
- `Aweme` 解析
- 视频 / 图文笔记下载与分发

适用命令：

```bash
python main.py douyin
```

### `platforms/instagram.py`

负责：

- Instagram 关注对象模型
- GraphQL 抓取
- 帖子解析
- 图片 / 视频下载与分发

适用命令：

```bash
python main.py instagram
```

### `platforms/bilibili.py`

负责：

- B 站关注对象模型
- 动态抓取
- 视频动态 / 图文动态解析
- Bilibili 视频下载与分发

适用命令：

```bash
python main.py bilibili
```

也支持别名：

```bash
python main.py bili
```

## 运维脚本

### `ops/manage.py`

一个 Telegram 管理脚本，主要用于：

- 查询关注用户
- 增加/修改关注对象
- 按平台筛选用户
- 手动重发部分内容

### `ops/nicefuturebot.py`

一个偏老的 Telegram 交互脚本，用来：

- 通过 Telegram 文本命令触发抓取
- 删除/重发消息
- 做简单的错误处理

### `ops/deal_error.py`

读取 `error.txt` 中失败记录，尝试重新处理失败的微博/抖音内容。

### `ops/chat_download.py`

使用 Telethon 从 Telegram 聊天历史中回拉媒体文件到本地。

### `ops/modify_msg.py`

批量编辑已经发送到 Telegram 的消息文本，一般用于修复历史消息格式或用户名。

### `ops/modify_msg_legacy.py`

旧版本修改脚本，功能与 `ops/modify_msg.py` 接近，建议仅作参考或历史保留。

## 安装要求

### Python

- Python 3.12+

### 依赖

项目依赖定义在 `pyproject.toml`。

推荐使用 `uv`：

```bash
uv sync
```

或使用 `pip`：

```bash
pip install -r requirements.txt
```

如果你完全依赖 `pyproject.toml`，也可以：

```bash
pip install -e .
```

## 环境变量

可参考 `.env.example`：

```env
# Telegram
TELEGRAM_BOT_TOKEN=
ERROR_TELEGRAM_BOT_TOKEN=

# MySQL
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_PORT=3306
MYSQL_DB=nicebot
```

### 说明

- `TELEGRAM_BOT_TOKEN`
  - 主发送 Bot 的 token

- `ERROR_TELEGRAM_BOT_TOKEN`
  - 当前代码里保留了错误通知相关变量，但主流程主要依赖 `TELEGRAM_BOT_TOKEN`

- `MYSQL_*`
  - 用于连接 MySQL

## 额外运行前提

### 1. Cookie 文件

项目依赖本地 cookie 文件，不同平台使用不同文件：

- 微博：`cookies/johnjohn01.txt`
- 抖音：`cookies/小号.txt`
- 抖音收藏/特殊场景：`cookies/大号.txt`
- Instagram：`cookies/neverblock11.txt`
- Bilibili：`cookies/bl.txt`

如果 cookie 失效，抓取会失败或返回空数据。

### 2. Telegram Bot API Server

当前发送逻辑默认连接本地 Telegram Bot API Server：

- `http://localhost:8081/bot`
- `http://localhost:8081/file/bot`

也就是说：

- 项目不是直接走默认公网 Bot API
- 需要本机/服务器已经部署并启动了本地 Bot API Server

相关代码在：

- `core/sender_dispatcher.py`
- `ops/nicefuturebot.py`

### 3. 下载目录

媒体下载根目录当前写死为：

```text
/root/download
```

定义位置：

- `core/utils.py`

这意味着：

- 在 Linux / Docker 环境下更自然
- 在 Windows 上运行时，建议先确认这个路径是否符合你的部署方式

## 数据库说明

### `user` 表

主流程依赖 `user` 表保存关注对象。

从代码使用方式看，至少需要这些字段：

- `userid`
- `username`
- `latest_time`
- `platform`
- `scrapy_time`
- `valid`

其中：

- `platform`：`weibo` / `douyin` / `instagram` / `bilibili`
- `valid`
  - `0`：取消关注
  - `1`：特别关注
  - `2`：普通关注

### `messages` 表

发送完成后，消息会写入 `messages` 表。

当前插入使用的核心字段包括：

- `MESSAGE_ID`
- `CAPTION`
- `CHAT_ID`
- `DATE_TIME`
- `FORM_USER`
- `CHAT`
- `MEDIA_GROUP_ID`
- `TEXT_RAW`
- `URL`
- `USERID`
- `USERNAME`
- `IDSTR`
- `MBLOGID`
- `MSG_STR`

该表主要用于：

- URL 去重
- 消息追踪
- 历史补发
- 管理脚本查询

## 常用运行方式

### 查看平台帮助

```bash
python main.py weibo --help
python main.py douyin --help
python main.py instagram --help
python main.py bilibili --help
```

### 抓取某个平台

```bash
python main.py weibo
python main.py douyin
python main.py instagram
python main.py bilibili
```

### 只抓取，不发送

```bash
python main.py weibo --no-send
```

这个模式下：

- 会抓取和下载
- 不发送 Telegram
- 不更新用户 `latest_time`

### 筛选部分用户

按 `userid`：

```bash
python main.py weibo --user-id 123456
```

按 `username`：

```bash
python main.py douyin --username favorite
```

按关注类型：

```bash
python main.py instagram --valid 1
python main.py bilibili --valid 1 2
```

按时间窗口：

```bash
python main.py weibo --latest-time-start "2026-03-01 00:00:00"
python main.py weibo --latest-time-end "2026-03-15 23:59:59"
```

### Instagram 本地 JSON 模式

```bash
python main.py instagram --local-json
```

### Bilibili 本地 JSON 模式

```bash
python main.py bilibili --local-json
```

## 日志与错误

### 日志目录

- 平台日志：`logs/`
- 发送记录：`logs/send.log`

### 错误记录

- `error.txt`

一些失败内容可以通过：

```bash
python ops/deal_error.py
```

重新处理。

## 媒体处理规则

公共限制定义在 `core/utils.py`：

- 图片上限：`10MB`
- 视频上限：`500MB`
- 文档上限：`500MB`

发送前会统一判断媒体类型：

- `photo`
- `video`
- `document`

Telegram 相册发送时还会做拆组，避免超出限制。

## 设计说明

这个项目现在采用的是：

- 平台实现单文件化：每个平台一个脚本
- 平台入口类注册：根入口只负责选择平台类并透传参数
- 核心能力集中化：统一模型、统一下载、统一发送
- 运维脚本隔离化：避免主抓取链路和辅助脚本混在一起

相比旧结构，当前结构的好处是：

- 更容易理解每个平台的完整流程
- 公共逻辑更集中
- 运维脚本不再和核心逻辑混放

## 已知情况

- 项目中仍保留少量历史脚本和旧风格代码
- `ops/manage.py`、`ops/modify_msg.py` 等脚本存在若干 `SyntaxWarning`，但不影响当前主抓取入口的基本使用
- 部分路径仍写死为 Linux 风格目录，如 `/root/download`
- 部分平台高度依赖登录 cookie，cookie 失效后需要人工更新

## 推荐使用方式

如果你只关心主抓取链路，重点看这几个位置：

- `main.py`
- `platforms/`
- `core/post.py`
- `core/downloader.py`
- `core/sender_dispatcher.py`
- `core/database.py`

如果你只关心管理和修复，重点看：

- `ops/manage.py`
- `ops/deal_error.py`
- `ops/nicefuturebot.py`

## 后续可继续优化的方向

- 把下载根目录改为环境变量配置
- 为数据库补充初始化 SQL
- 清理历史运维脚本里的硬编码 token
- 为 `ops/` 脚本补充更清晰的使用说明
- 增加最基本的单元测试和集成测试
