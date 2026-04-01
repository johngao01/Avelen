# Avelen

`Avelen` 是一个面向个人使用的“多平台内容抓取 + Telegram 分发 + MySQL 去重留痕”项目。

它会从数据库中的关注列表读取目标账号，按平台抓取最新内容，统一转换成内部 `Post` 数据结构，下载媒体文件，发送到 Telegram，然后把发送结果写回 MySQL，供后续去重、补发、审计和运维脚本使用。

当前已接入平台：

- 微博 `weibo`
- 抖音 `douyin`
- Instagram `instagram`
- Bilibili `bilibili`

这份 README 重点解决四件事：

- 这个项目整体是怎么工作的
- 每个脚本文件到底负责什么
- 应该怎么运行主流程和运维脚本
- 数据库至少需要有哪些表和字段

说明：

- 文中数据库设计是根据代码实际访问字段反推出来的“最低可运行结构”，仓库里没有提供正式 DDL
- `ops/` 目录脚本很多是作者自用工具，副作用较强，运行前一定要先看路径、Token、Chat ID、SQL 条件

## 1. 项目解决什么问题

这个项目的目标很明确：

1. 从多个平台抓取指定用户的新内容。
2. 把平台差异收敛成统一模型。
3. 下载图片、视频等媒体到本地。
4. 通过 Telegram Bot 把媒体和正文发到固定聊天。
5. 把发送结果记入 MySQL，避免重复发送，并支持补发、删改、巡检。

如果你把它理解成一个“个人订阅与投递系统”，是准确的。

## 2. 总体架构

### 2.1 主流程

```text
MySQL user 表
  -> 筛选需要抓取的关注对象
  -> 按平台分发到对应抓取器
  -> 平台接口抓取 / 本地 JSON 回放
  -> 解析为统一 BasePost / MediaItem
  -> Downloader 下载媒体
  -> sender_dispatcher 发送到 Telegram
  -> MySQL messages 表落库
  -> 回写 user.latest_time / user.scrapy_time
```

### 2.2 关键设计

- 统一入口：`main.py`
- 统一平台注册：`platforms/__init__.py`
- 统一数据模型：`core/models.py`
- 统一 CLI、筛选、执行壳层：`core/scrapy_runner.py`
- 统一下载器：`core/downloader.py`
- 统一 Telegram 发送器：`core/sender_dispatcher.py`
- 统一数据库访问：`core/database.py`
- 统一配置：`core/settings.py`

## 3. 目录结构

```text
weibo_tg_bot/
├─ main.py
├─ README.md
├─ pyproject.toml
├─ requirements.txt
├─ .env.example
├─ Dockerfile
├─ config/
│  └─ platforms.toml
├─ core/
│  ├─ __init__.py
│  ├─ database.py
│  ├─ downloader.py
│  ├─ models.py
│  ├─ scrapy_runner.py
│  ├─ sender_dispatcher.py
│  ├─ settings.py
│  └─ utils.py
├─ platforms/
│  ├─ __init__.py
│  ├─ weibo.py
│  ├─ douyin.py
│  ├─ instagram.py
│  └─ bilibili.py
├─ ops/
│  ├─ __init__.py
│  ├─ manage.py
│  ├─ nicefuturebot.py
│  ├─ deal_error.py
│  ├─ chat_download.py
│  ├─ modify_msg.py
│  ├─ delete_messages.py
│  ├─ check_post_delivery.py
│  └─ package.py
├─ cookies/
├─ logs/
└─ chat_download_history.json
```

## 4. 运行前准备

### 4.1 Python 版本

要求：

- Python `3.12+`

### 4.2 安装依赖

推荐使用 `uv`：

```bash
uv sync
```

或者：

```bash
pip install -r requirements.txt
```

也可以：

```bash
pip install -e .
```

### 4.3 主要依赖用途

- `requests`：抓取平台接口
- `python-telegram-bot`：Telegram 发送与管理 Bot
- `telethon`：下载 Telegram 历史媒体
- `pymysql`：MySQL 访问
- `loguru`：日志
- `rich`：下载进度展示
- `yt-dlp`：Bilibili 视频下载
- `opencv-python-headless`、`pillow`：识别媒体信息
- `filelock`：发送锁、错误通知锁
- `gmssl`：抖音签名计算

## 5. 配置说明

### 5.1 环境变量

参考 [.env.example](./.env.example)：

```env
# Telegram
TELEGRAM_BOT_TOKEN=
ERROR_TELEGRAM_BOT_TOKEN=
TELEGRAM_LOCAL_MODE=1

# MySQL
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_PORT=3306
MYSQL_DB=nicebot
```

主流程最重要的变量：

- `TELEGRAM_BOT_TOKEN`
- `MYSQL_HOST`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_PORT`
- `MYSQL_DB`

可选变量：

- `ERROR_TELEGRAM_BOT_TOKEN`
  作用：抓取失败时通过另一个 Bot 发错误通知
- `TELEGRAM_LOCAL_MODE`
  作用：是否走本地 Bot API Server
  - `1` / 默认：使用本地模式
  - `0`：使用官方默认 Telegram Bot API
- `TELEGRAM_BASE_URL`
  默认值：`http://localhost:8081/bot`
- `TELEGRAM_BASE_FILE_URL`
  默认值：`http://localhost:8081/file/bot`
- `DOWNLOAD_ROOT`
  作用：覆盖 `config/platforms.toml` 中的下载根目录

### 5.2 平台配置

平台配置位于 [config/platforms.toml](./config/platforms.toml)。

它定义了：

- 默认下载目录
- 公共请求头
- 各平台基础 URL
- 各平台 Cookie 文件名

当前默认配置大意如下：

- 下载根目录：`/root/download`
- 微博 Cookie：`cookies/johnjohn01.txt`
- 抖音 Cookie：`cookies/小号.txt`
- 抖音喜欢页 Cookie：`cookies/大号.txt`
- B站 Cookie：`cookies/bl.txt`
- Instagram Cookie：`cookies/neverblock11.txt`

### 5.3 Cookie 文件

项目强依赖 Cookie。没有 Cookie 或 Cookie 失效时，最常见的表现是：

- 返回空数据
- 接口报错
- 需要登录
- 被限流或风控

Cookie 文件放在 `cookies/` 目录下，文件名需和 `config/platforms.toml` 对应。

## 6. 下载目录与 JSON 缓存

默认规则：

- 媒体文件：`<DOWNLOAD_ROOT>/<platform>/<username>/<filename>`
- JSON 缓存：`<DOWNLOAD_ROOT>/<platform>/json/<username>/<filename>`

示例：

```text
/root/download/weibo/某用户/20260331_xxx.jpg
/root/download/douyin/json/favorite/1234567890123456789.json
/root/download/bilibili/json/某用户/Dynamic_1234567890.json
```

本地 JSON 的意义：

- 抓取时把原始响应存档
- 出问题时可以离线回放
- 支持 `--json` / `--local-json` 模式

## 7. 主流程怎么运行

### 7.1 统一入口

查看帮助：

```bash
python main.py --help
```

按平台运行：

```bash
python main.py weibo
python main.py douyin
python main.py instagram
python main.py bilibili
```

`bilibili` 还支持别名：

```bash
python main.py bili
```

### 7.2 不指定平台

可以直接：

```bash
python main.py
```

这时程序会：

1. 先按 CLI 条件从 `user` 表筛选记录。
2. 根据筛中的 `platform` 字段自动分发到对应平台抓取器。

这很适合跑一个“全平台巡检任务”。

### 7.3 常用命令示例

只抓微博：

```bash
python main.py weibo
```

只抓某个用户名模糊命中的用户：

```bash
python main.py weibo -rn 糕
python main.py -rn 糕
```

按 userid 精确筛选：

```bash
python main.py weibo -id 123456
python main.py bilibili -id 987654
```

只展示筛中的用户，不执行抓取：

```bash
python main.py weibo -l
python main.py -l -rn 糕
```

只下载不发送：

```bash
python main.py weibo -n
```

从本地 JSON 回放：

```bash
python main.py weibo -j
python main.py instagram -j
```

覆盖 `latest_time`，强制多抓历史：

```bash
python main.py weibo -slt
python main.py weibo -slt "2024-01-01 00:00:00"
```

按时间范围筛选：

```bash
python main.py weibo --lts "2026-03-01 00:00:00" --lte "2026-03-31 23:59:59"
python main.py douyin --sts "2026-03-01 00:00:00"
```

自定义排序：

```bash
python main.py -l -s latest_time:asc
python main.py -l -s username:asc
python main.py -l -s valid:desc
```

## 8. CLI 参数说明

主入口和各平台入口使用同一套参数，定义在 `core/scrapy_runner.py`。

### 8.1 过滤类参数

- `-v`, `--valid`
  关注类型，可多选；默认是 `1`
- `-id`, `--uid`, `--user-id`
  按 `user.userid` 精确筛选，可重复传参
- `--name`, `--username`
  按 `user.username` 精确筛选，可重复传参
- `-rn`, `--rename`
  按 `user.username` 模糊筛选
- `--lts`, `--latest-time-start`
- `--lte`, `--latest-time-end`
- `--sts`, `--scrapy-time-start`
- `--ste`, `--scrapy-time-end`

### 8.2 行为控制参数

- `-s`, `--sort`
  格式：`字段[:asc|desc]`
- `-slt`, `--set-latest-time`
  临时覆盖本次运行中筛到用户的 `latest_time`
- `-n`, `--no-send`
  只抓取和下载，不发 Telegram，也不更新 `user.latest_time`
- `-p`, `--progress`, `--download-progress`
  注意：这个参数在代码里是“关闭进度条”的开关，传了以后会让 `download_progress=False`
- `-j`, `--json`, `--local-json`
  从本地 JSON 读取
- `-l`, `--list`
  只展示筛选到的 `user` 记录

### 8.3 `valid` 取值

- `-2`：账号失效或被平台删除
- `-1`：不再追踪
- `0`：取消关注
- `1`：特别关注
- `2`：普通关注

### 8.4 `sort` 支持字段

- `scrapy_time`
- `latest_time`
- `username`
- `userid`
- `platform`
- `valid`

兼容别名：

- `scrapy-time`
- `latest-time`
- `user-id`
- `user_id`

## 9. 各平台行为差异

### 9.1 微博 `platforms/weibo.py`

抓取来源：

- 普通账号：`ajax/statuses/mymblog`
- 喜欢页用户 `favorite`：`ajax/statuses/likelist`

主要特点：

- 支持图片、视频、图文混合、LivePhoto
- 会保存微博原始 JSON 到本地
- 过滤掉转发微博、纯文字微博、V+ 微博
- 普通用户会以 `latest_time` 做增量过滤
- `favorite` 模式会抓取一定数量上限，默认上限来自 `SCRAPY_FAVORITE_LIMIT`

### 9.2 抖音 `platforms/douyin.py`

抓取来源：

- 发布页接口：`aweme/post`
- 喜欢页接口：`aweme/favorite`
- 单条详情接口：`aweme/detail`

主要特点：

- 内置 `X-Bogus` / `A-Bogus` 相关签名逻辑
- 支持视频、图文、图文中的附带视频
- 会保存 aweme JSON
- 视频时长超过 30 分钟直接跳过

### 9.3 Instagram `platforms/instagram.py`

抓取来源：

- GraphQL：`graphql/query`

主要特点：

- 启动时会先访问首页获取 `fb_dtsg`
- 按用户时间线分页抓取
- 支持单图、单视频、轮播
- 会跳过置顶内容
- 会保存 JSON 供离线回放

### 9.4 Bilibili `platforms/bilibili.py`

抓取来源：

- 动态接口：`x/polymer/web-dynamic/v1/feed/space`

主要特点：

- 支持视频动态和图文动态
- 视频下载走 `yt-dlp`
- `yt-dlp` 生成的 `.info.json` 会被挪到平台 JSON 目录
- 图文正文不足时会访问 `opus/<id>` 页面补正文
- 会跳过粉丝专属、充电专属、超长视频
- 支持别名 `bili`

## 10. 文件级说明

这一节按“看代码时的认知顺序”写，尽量让人和 AI 一眼知道每个脚本是做什么的。

### 10.1 顶层文件

#### `main.py`

项目统一入口。

职责：

- 解析平台参数
- 构造统一 CLI
- 如果指定平台，则运行对应平台类
- 如果不指定平台，则先查 `user` 表，再按 `platform` 自动分发

适合什么时候看：

- 你想理解程序从哪里启动
- 你想做全平台运行
- 你想接新的平台入口

#### `pyproject.toml`

项目元数据和依赖定义。

你可以从这里快速看出：

- Python 版本要求
- 依赖列表
- 包名是 `avelen`

#### `.env.example`

环境变量模板。

#### `Dockerfile`

容器化运行用的基础镜像配置文件。

#### `chat_download_history.json`

`ops/chat_download.py` 使用的历史进度文件，记录每个 Telegram chat 的下载游标和标题。

### 10.2 `config/`

#### `config/platforms.toml`

平台配置中心。

职责：

- 约定下载目录
- 维护 Cookie 文件名
- 管理公共请求头和平台基础 URL

### 10.3 `core/`

#### `core/__init__.py`

空初始化文件，无业务逻辑。

#### `core/settings.py`

全局配置与运行时常量入口。

职责：

- 读取 `config/platforms.toml`
- 生成下载目录、JSON 目录、Cookie 路径、日志路径
- 读取 Telegram、本地 Bot API、错误通知等环境变量
- 暴露全局常量供其他模块直接导入

这是整个项目的“配置根”。

#### `core/models.py`

统一数据模型与抽象基类。

核心对象：

- `FollowUser`
  跨平台关注用户模型
- `MediaItem`
  平台层交给下载层的统一媒体描述
- `DownloadTask`
  下载器内部任务对象
- `DownloadedFile`
  下载完成后的标准文件描述
- `PostData`
  发送层使用的统一 payload
- `BasePlatform`
  平台抓取器抽象基类
- `BasePost`
  平台内容对象抽象基类
- `RunOptions`
  执行链路参数对象

如果你要新接一个平台，最重要的就是先看这个文件。

#### `core/database.py`

数据库访问层。

职责：

- 创建 MySQL 连接
- 插入 `messages`
- 查询 `user`
- 根据 CLI 参数安全拼接筛选 SQL
- 查询是否已发送过某条内容
- 更新 `user.latest_time` 和 `user.scrapy_time`
- 提供一些运维脚本使用的去重、删除、反查能力

这个文件可以视为“当前项目隐式数据库契约”的主要来源。

#### `core/scrapy_runner.py`

各平台共用的执行壳层。

职责：

- 定义统一 CLI 参数
- 把 CLI 参数转成数据库筛选条件
- 渲染 `user` 表筛选结果
- 驱动“查询用户 -> 逐用户执行 -> 记录日志”的主循环
- 协调下载与发送结果

如果说 `main.py` 是总入口，这个文件就是“主流程编排器”。

#### `core/downloader.py`

统一下载器。

职责：

- 把 `MediaItem` 变成 `DownloadTask`
- 并发下载媒体
- 显示 Rich 进度条
- 根据媒体类型识别最终 Telegram 发送方式
- 自动处理 B站视频 `yt-dlp` 下载
- 返回标准化 `DownloadedFile`

额外逻辑：

- 识别微博某些“防和谐占位文件”并标记跳过
- 自动识别图片分辨率、视频时长、文件大小
- 判断是按 `photo`、`video` 还是 `document` 发送

#### `core/sender_dispatcher.py`

统一 Telegram 发送器。

职责：

- 把同一条 Post 的媒体按图片、视频、文档分类发送
- 最后补发一条正文消息
- 发送后立即写入 `messages` 表
- 用文件锁保证发送串行，避免多个抓取器交叉发送

发送顺序是：

1. 图片
2. 视频
3. 文档
4. 最终文字消息

#### `core/utils.py`

工具函数集合。

职责：

- 构造平台下载目录和 JSON 路径
- 构造浏览器请求头
- 读取文本文件
- 发送错误通知
- 发送频率控制
- 错误日志记录
- Netscape Cookie 解析

### 10.4 `platforms/`

#### `platforms/__init__.py`

平台注册中心。

职责：

- 注册所有平台类
- 生成 `PLATFORM_REGISTRY`
- 根据名称或别名返回平台类

#### `platforms/weibo.py`

微博抓取器与微博 Post 解析器。

主要内容：

- `Following`：微博关注对象
- `WeiboPost`：微博内容对象
- `WeiboScrapy`：微博平台执行器
- `build_weibo_post()`：单条微博构造
- `handle_weibo()`：旧脚本兼容入口

使用方式：

```bash
python main.py weibo
python platforms/weibo.py -l
```

#### `platforms/douyin.py`

抖音抓取器与作品解析器。

主要内容：

- `Following`
- `Aweme`
- `DouyinScrapy`
- `get_url_id()`：从分享文本/短链提取作品 URL 和 `aweme_id`
- `get_aweme_detail()`：拉单条详情
- `handler_douyin()`：旧脚本兼容入口

使用方式：

```bash
python main.py douyin
python platforms/douyin.py -j
```

#### `platforms/instagram.py`

Instagram 抓取器与内容解析器。

主要内容：

- `parse_cookie_header()`：解析 Cookie 头
- `build_instagram_headers()`：构造 GraphQL 请求头
- `InstagramPost`
- `InstagramScrapy`
- `InstagramPlatform`：对外兼容别名

使用方式：

```bash
python main.py instagram
python platforms/instagram.py -l
```

#### `platforms/bilibili.py`

B站抓取器与动态解析器。

主要内容：

- `BilibiliPost`
- `BilibiliScrapy`
- `get_opus_desc()`：补抓图文正文

使用方式：

```bash
python main.py bilibili
python main.py bili
```

### 10.5 `ops/`

这部分脚本不是统一主流程的一部分，而是围绕 `messages`、Telegram、历史媒体、人工修复做的运维工具。

强提醒：

- 多数脚本带真实副作用
- 有些脚本里写死了 Token、路径、Chat ID、SQL 条件
- 不建议在不审查代码的情况下直接运行

#### `ops/__init__.py`

空初始化文件，无业务逻辑。

#### `ops/manage.py`

Telegram 管理 Bot。

主要用途：

- 在 Telegram 内管理 `user` 表关注对象
- 搜索用户
- 查看某个用户当前状态
- 新增关注
- 修改 `valid` 状态
- 直接处理单条微博或抖音链接

运行方式：

```bash
python ops/manage.py
```

使用特点：

- 通过 `python-telegram-bot` 轮询运行
- 会监听文本、URL、回调按钮
- 支持 `/manage`、`/lm`、`/myfollow`
- 能直接把发来的微博/抖音链接拉取并投递

注意：

- 脚本中写死了 Bot Token、本地 Bot API 地址、开发者 Chat ID
- 运行前请先改成你自己的配置

#### `ops/nicefuturebot.py`

旧版 Telegram 运维 Bot。

主要用途：

- 通过 Bot 命令删除、补发、清理重复消息
- 通过文本命令触发 `python main.py weibo` / `douyin`
- 处理消息反应后自动删除或重发

运行方式：

```bash
python ops/nicefuturebot.py
```

常见命令和行为：

- `/resend`
- `/delete`
- `/clear`
- 文本 `sw`、`sd`
- 对消息打表情反应触发删改逻辑

注意：

- 也写死了 Token 和本地 Bot API 地址
- 直接联动数据库和 Telegram 删除操作

#### `ops/deal_error.py`

错误日志补偿脚本。

主要用途：

- 读取错误日志中的微博/抖音 URL
- 判断该内容是否已经发送过
- 对未发送成功的内容执行补发
- 把仍失败的记录重新写回错误文件

运行方式：

```bash
python ops/deal_error.py
```

注意：

- 默认读取的是上一级目录的 `../error.txt`
- 这个路径和现在主流程用的 `logs/error.txt` 不完全一致，运行前请先核对

#### `ops/chat_download.py`

从 Telegram 历史聊天中回拉媒体文件。

主要用途：

- 使用 `Telethon` 读取群/频道历史
- 下载媒体组中的文件
- 把同一媒体组按消息文案归档到目录
- 把下载进度写回 `chat_download_history.json`

运行方式：

```bash
python ops/chat_download.py
```

注意：

- 脚本中写死了 `api_id`、`api_hash`、代理和下载目录
- 依赖 `FastTelethonhelper`

#### `ops/modify_msg.py`

批量修改 Telegram 已发送文字消息，并同步更新数据库中的 `msg_str` / `username`。

主要用途：

- 按 SQL 条件批量读取 `messages`
- 用新的用户名重新生成 Markdown 文本
- 调用 `edit_message_text`
- 更新数据库中的原始消息 JSON

运行方式：

```bash
python ops/modify_msg.py
```

注意：

- 脚本中硬编码了 SQL 条件，例如固定 `idstr`
- 这是典型的一次性修复工具，不是通用命令

#### `ops/delete_messages.py`

按 SQL 条件批量删除历史发送记录的运维脚本。

主要用途：

- 从 `messages` 表筛出待处理消息
- 按 `idstr` 把同一个 post 的多条 Telegram 消息聚合起来
- 先删 Telegram 消息，再删本地下载文件，最后按需删除数据库记录
- 以流式方式逐个 post 输出进度，避免先汇总全部结果再开始处理

运行方式：

```bash
python ops/delete_messages.py --where "USERNAME=%s AND USERID<>%s" --param "奶糖白大兔" --param "2319874553"
python ops/delete_messages.py --where "IDSTR=%s" --param "1234567890" --execute
python ops/delete_messages.py --where "IDSTR=%s" --param "1234567890" --delete-db --execute
```

当前行为：

- 默认只预览，不做实际删除
- 加 `--execute` 后才真正执行
- 默认删除 Telegram 和本地文件
- 只有额外加 `--delete-db` 时才删除 `messages` 表记录
- 加 `--skip-telegram` 可只删文件/数据库
- 加 `--skip-files` 可只删 Telegram/数据库

实现细节：

- 只按 `idstr` 识别同一条 post
- 查询默认只看最近 `56` 小时的消息
- 其中 `48` 小时对应 Telegram 删除窗口，额外 `8` 小时用于抵消 `messages.DATE_TIME` 以 UTC 入库、服务器时间为东八区的偏移
- 日志会写入 `logs/delete_messages.log`

注意：

- `--where` 建议优先配合 `--param` 使用，避免引号和转义问题
- 如果 Telegram 已拒绝删除，脚本仍会继续后续 post，并把失败写到日志
- 本地文件是按 `CAPTION` 作为文件名在 `DOWNLOAD_ROOT` 下递归查找的，运行前请确认你的落盘命名方式没有偏离当前主流程

#### `ops/check_post_delivery.py`

发送完整性巡检脚本。

主要用途：

- 检查 `messages` 表中每个 post 的发送是否完整
- 识别漏发、错位发送、重复发送
- 输出摘要统计

运行方式：

```bash
python ops/check_post_delivery.py
python ops/check_post_delivery.py --summary-only
python ops/check_post_delivery.py --status missing
python ops/check_post_delivery.py --url "https://www.weibo.com/..."
```

支持的状态：

- `complete`
- `misordered`
- `missing`
- `duplicate_send`
- `unknown`

这个脚本是 `ops/` 里最“可复用”的一个。

#### `ops/package.py`

本地媒体打包脚本。

主要用途：

- 把 `/root/download/` 下所有文件打进 `/media/media.zip`
- 打包完成后删除原文件
- 清理空目录
- 输出一个下载链接

运行方式：

```bash
python ops/package.py
```

注意：

- 这是强副作用脚本
- 会删除原下载目录中的文件
- 默认路径是 Linux 服务器路径，Windows 上不能直接照搬

## 11. 数据库设计

仓库没有提供建表 SQL，但代码强依赖两个核心表：

- `user`
- `messages`

另外 `ops/manage.py` 还访问了一个 `statistic` 表。

下面是根据代码反推的“最低可用设计”。

### 11.1 `user` 表

作用：

- 存储关注对象
- 控制抓取范围
- 记录增量抓取游标

代码实际依赖字段：

| 字段名 | 类型建议 | 是否关键 | 说明 |
| --- | --- | --- | --- |
| `userid` | `varchar(128)` | 是 | 平台用户唯一标识。微博/B站一般是数字字符串，抖音是 `sec_uid`，Instagram 这里存的是用户名或 profile 标识 |
| `username` | `varchar(255)` | 是 | 你在系统内给这个关注对象起的名字，不一定等于平台昵称 |
| `latest_time` | `datetime` | 是 | 已处理到的最新作品时间；用于增量抓取 |
| `platform` | `varchar(32)` | 是 | 平台标识：`weibo` / `douyin` / `instagram` / `bilibili` |
| `scrapy_time` | `datetime` | 是 | 最后一次执行抓取的时间 |
| `valid` | `int` | 是 | 关注状态，见下文 |

推荐索引：

- 唯一索引：`(platform, userid)`
- 普通索引：`valid`
- 普通索引：`latest_time`
- 普通索引：`scrapy_time`
- 普通索引：`username`

推荐建表草案：

```sql
CREATE TABLE `user` (
  `userid` varchar(128) NOT NULL,
  `username` varchar(255) NOT NULL,
  `latest_time` datetime DEFAULT NULL,
  `platform` varchar(32) NOT NULL,
  `scrapy_time` datetime DEFAULT NULL,
  `valid` int NOT NULL DEFAULT 2,
  PRIMARY KEY (`platform`, `userid`),
  KEY `idx_user_valid` (`valid`),
  KEY `idx_user_latest_time` (`latest_time`),
  KEY `idx_user_scrapy_time` (`scrapy_time`),
  KEY `idx_user_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### `valid` 字段解释

| 值 | 含义 |
| --- | --- |
| `-2` | 账号失效 / 被平台删除 |
| `-1` | 不再追踪 |
| `0` | 取消关注 |
| `1` | 特别关注 |
| `2` | 普通关注 |

主流程默认只抓 `valid in (1)`，如果你显式传参则可覆盖。

### 11.2 `messages` 表

作用：

- 记录 Telegram 发送结果
- 作为去重依据
- 提供后续删除、补发、巡检、修复的数据基础

代码明确使用到的字段：

| 字段名 | 类型建议 | 是否关键 | 说明 |
| --- | --- | --- | --- |
| `MESSAGE_ID` | `bigint` | 是 | Telegram 消息 ID |
| `CAPTION` | `text` | 是 | 媒体消息 caption；纯文字消息通常为空 |
| `CHAT_ID` | `varchar(64)` | 是 | Telegram chat id |
| `DATE_TIME` | `datetime` | 是 | Telegram 消息发送时间 |
| `FORM_USER` | `varchar(64)` | 否 | Telegram 返回的发送者 ID，代码里拼写就是 `FORM_USER` |
| `CHAT` | `varchar(64)` | 否 | Telegram chat 字段的另一份记录 |
| `MEDIA_GROUP_ID` | `varchar(128)` | 否 | 相册组 ID |
| `TEXT_RAW` | `longtext` | 是 | 原始正文文本 |
| `URL` | `varchar(1024)` | 是 | 对应平台内容链接 |
| `USERID` | `varchar(128)` | 是 | 平台用户 ID |
| `USERNAME` | `varchar(255)` | 是 | 系统内用户名或显示用户名 |
| `CREATE_TIME` | `datetime` | 否 | 原平台内容创建时间。代码会写入，但 `MESSAGES` 常量里没列出，建议显式保留 |
| `IDSTR` | `varchar(255)` | 是 | 平台内容主 ID |
| `MBLOGID` | `varchar(255)` | 否 | 微博/B站等附加内容 ID |
| `MSG_STR` | `longtext` | 是 | Telegram 原始消息 JSON |

推荐索引：

- `URL`
- `IDSTR`
- `USERID`
- `DATE_TIME`
- `(URL, CAPTION)`

推荐建表草案：

```sql
CREATE TABLE `messages` (
  `MESSAGE_ID` bigint NOT NULL,
  `CAPTION` text,
  `CHAT_ID` varchar(64) DEFAULT NULL,
  `DATE_TIME` datetime DEFAULT NULL,
  `FORM_USER` varchar(64) DEFAULT NULL,
  `CHAT` varchar(64) DEFAULT NULL,
  `MEDIA_GROUP_ID` varchar(128) DEFAULT NULL,
  `TEXT_RAW` longtext,
  `URL` varchar(1024) DEFAULT NULL,
  `USERID` varchar(128) DEFAULT NULL,
  `USERNAME` varchar(255) DEFAULT NULL,
  `CREATE_TIME` datetime DEFAULT NULL,
  `IDSTR` varchar(255) DEFAULT NULL,
  `MBLOGID` varchar(255) DEFAULT NULL,
  `MSG_STR` longtext,
  KEY `idx_messages_url` (`URL`(255)),
  KEY `idx_messages_idstr` (`IDSTR`),
  KEY `idx_messages_userid` (`USERID`),
  KEY `idx_messages_datetime` (`DATE_TIME`),
  KEY `idx_messages_url_caption` (`URL`(255), `CAPTION`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

说明：

- 这里没有强行设主键，因为现有代码的插入方式没有显式处理重复主键
- 如果你要做更强约束，建议另加自增主键 `id`

### 11.3 `messages` 表里的业务含义

同一个平台内容通常会对应多条 Telegram 记录：

- 若干条媒体消息
- 最后一条总结文字消息

所以一个内容在 `messages` 表里可能对应多行。

也是因为这个设计，`ops/check_post_delivery.py` 才能根据一组消息判断：

- 是否漏发
- 是否文字先于媒体发送
- 是否重复发过

### 11.4 `statistic` 表

`ops/manage.py` 里有一条 SQL：

```sql
select username from statistic order by num desc
```

说明作者环境里还存在一个 `statistic` 表，但主抓取链路并不依赖它。

如果你不用 `ops/manage.py` 的 `/myfollow` 功能，可以先不建。

## 12. Telegram 发送机制

默认发送目标是代码里写死的开发者聊天：

- `DEVELOPER_CHAT_ID = 708424141`

默认发送方式：

- 优先使用本地 Bot API Server
- 地址默认是：
  - `http://localhost:8081/bot`
  - `http://localhost:8081/file/bot`

如果不想用本地模式，可以设置：

```env
TELEGRAM_LOCAL_MODE=0
```

发送细节：

- 同一个 Post 的发送被文件锁串行化
- 媒体和文字分开发送
- 每一批发送成功后立即写库

## 13. 日志与错误处理

日志目录默认是 `logs/`。

重要文件：

- `logs/scrapy_main.log`
- `logs/scrapy_weibo.log`
- `logs/scrapy_douyin.log`
- `logs/scrapy_instagram.log`
- `logs/scrapy_bilibili.log`
- `logs/send.log`
- `logs/error.txt`
- `logs/error_notify_state.json`

错误处理机制：

- 抓取异常会写日志
- 关键抓取错误会尝试通过错误通知 Bot 推送
- 会用去重状态文件避免同一错误反复轰炸

## 14. 新人或 AI 最推荐的阅读顺序

如果你第一次接手这个项目，推荐按这个顺序看：

1. `main.py`
2. `core/scrapy_runner.py`
3. `core/models.py`
4. `core/database.py`
5. `core/downloader.py`
6. `core/sender_dispatcher.py`
7. `platforms/weibo.py`
8. `platforms/douyin.py`
9. `platforms/instagram.py`
10. `platforms/bilibili.py`

如果你是为了排查“为什么消息没发对”，优先看：

1. `core/sender_dispatcher.py`
2. `core/database.py`
3. `ops/check_post_delivery.py`
4. `ops/deal_error.py`

## 15. 常见风险与注意事项

- 这个项目高度依赖 Cookie，Cookie 失效是最常见故障来源
- `ops/` 脚本很多写死了作者环境配置，不能直接照搬到新环境
- `ops/package.py` 会删除已打包原文件，运行前务必确认路径
- Telegram 相关脚本默认都指向固定 Chat ID
- 主流程默认只抓 `valid=1` 的用户，如果你以为会抓全部关注，这是一个容易踩坑的点
- `-p` 参数在当前代码里实际上是关闭进度条，不是开启进度条
- `messages` 表结构在代码里存在轻微不一致：
  `process_message()` 会生成 `CREATE_TIME`，但 `MESSAGES` 常量没有包含它；如果你要长期维护，建议统一修正

## 16. 最简启动清单

如果你想尽快跑起来，按这个顺序做：

1. 安装 Python 3.12+ 与依赖
2. 配置 `.env`
3. 准备 MySQL，并至少建好 `user` 和 `messages`
4. 把各平台 Cookie 文件放到 `cookies/`
5. 确认 Telegram Bot 和目标聊天可用
6. 如使用本地 Bot API，确认 `localhost:8081` 可访问
7. 往 `user` 表插入至少一条待抓取用户
8. 执行：

```bash
python main.py weibo -l
python main.py weibo
```

如果 `-l` 能列出你预期的用户，说明数据库筛选链路已经通了。

## 17. 一句话总结

这是一个已经具备统一架构的个人多平台抓取与 Telegram 投递系统。

主流程部分已经比较清晰：`main.py` 负责编排，`platforms/` 负责抓取与解析，`core/` 负责下载、发送、数据库和配置；`ops/` 则是一组围绕历史数据、人工修复和 Telegram 管理的运维工具箱。
