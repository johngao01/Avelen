# Avelen

Avelen 是一个面向个人使用的多平台内容抓取与 Telegram 分发项目。

名字取意于爱情、追随与陪伴：安静地跟随关注对象，持续地抓取更新，并把重要内容稳定送达到 Telegram。

当前支持平台：

- 微博
- 抖音
- Instagram
- Bilibili

项目会轮询数据库中的关注对象，抓取新内容，统一整理为内部 `Post` 结构，下载媒体文件，然后通过 Telegram Bot 发送，并把发送结果写入 MySQL，以便去重、补发和后续管理。

## 项目特点

- 统一入口：`main.py` 根据平台名选择对应抓取器运行
- 统一模型：四个平台都收敛到 `BasePost` / `MediaItem`
- 统一下载：`core/downloader.py` 负责并发下载、进度条、Bilibili `yt-dlp`
- 统一发送：`core/sender_dispatcher.py` 串行发送到 Telegram 并即时落库
- 统一配置：`core/settings.py` 在导入时只读取一次 `config/platforms.toml`
- 统一目录：媒体和 JSON 都按平台 / 用户名组织

## 当前结构

```text
avelen/
  main.py
  README.md
  pyproject.toml
  requirements.txt
  .env.example

  config/
    platforms.toml

  core/
    database.py
    downloader.py
    models.py
    scrapy_runner.py
    sender_dispatcher.py
    settings.py
    utils.py

  platforms/
    __init__.py
    weibo.py
    douyin.py
    instagram.py
    bilibili.py

  ops/
    manage.py
    nicefuturebot.py
    deal_error.py
    chat_download.py
    modify_msg.py
    modify_msg_legacy.py

  cookies/
  logs/
```

## 核心流程

```text
main.py
  -> platforms registry
  -> 选择平台类
  -> 查询 user 表关注对象
  -> 抓取平台内容
  -> 转成 BasePost / MediaItem
  -> Downloader 下载媒体
  -> sender_dispatcher 发送 Telegram
  -> messages 表写入发送记录
  -> user 表更新 latest_time / scrapy_time
```

## 核心模块说明

### `main.py`

统一入口，只负责：

- 解析平台名
- 从 `platforms` 注册表选择平台类
- 将剩余参数透传给平台的 `run()` 方法

### `platforms/`

每个平台一个脚本，负责：

- 平台关注对象模型
- 平台原始数据抓取
- 平台 `Post` 解析
- 本地 JSON 回放
- 进入公共抓取 / 下载 / 发送流程

当前平台类：

- `WeiboScrapy`
- `DouyinScrapy`
- `InstagramScrapy`（对外兼容 `InstagramPlatform`）
- `BilibiliScrapy`

其中 Bilibili 还支持别名：

- `bili`

### `core/models.py`

统一数据模型与抽象基类：

- `FollowUser`
- `MediaItem`
- `BasePost`
- `BasePlatform`
- `get_platform_logger()`

`BasePost.__str__()` 现在统一输出创建时间、URL 和文案摘要，平台日志不再额外维护一套重复格式化函数。

### `core/scrapy_runner.py`

平台公共运行壳层，负责：

- 构建公共 CLI 参数
- 按条件筛选数据库中的关注对象
- 控制 `--no-send`
- 控制 `--download-progress` / `--no-download-progress`
- 统一执行“抓取 -> 过滤 -> 下载 -> 发送 -> 回写数据库”

### `core/downloader.py`

统一下载器，负责：

- 将 `BasePost.build_media_items()` 转成 `DownloadTask`
- 多文件并发下载
- Rich 下载进度条
- Bilibili 视频自动切换到 `yt-dlp`
- 下载结果统一转成发送层可直接消费的数据

### `core/sender_dispatcher.py`

统一 Telegram 发送器，负责：

- 串行发送，避免多抓取任务交错
- 文件和文本消息分别发送
- 发送完成后立即写入 `messages` 表

### `core/settings.py`

统一配置入口，职责很简单：

- 只负责全局配置和运行时开关
- 启动时读取一次 `config/platforms.toml`
- 暴露下载目录、Cookie 路径、日志路径、平台配置等常量

## 配置说明

### 1. Python 与依赖

要求：

- Python 3.12+

推荐使用 `uv`：

```bash
uv sync
```

或使用 `pip`：

```bash
pip install -r requirements.txt
```

如果你使用 `pyproject.toml` 安装：

```bash
pip install -e .
```

### 2. 环境变量

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

主流程实际依赖的核心环境变量：

- `TELEGRAM_BOT_TOKEN`
- `MYSQL_HOST`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_PORT`
- `MYSQL_DB`

可选环境变量：

- `DOWNLOAD_ROOT`
  作用：覆盖 `config/platforms.toml` 中的默认下载根目录
- `TELEGRAM_LOCAL_MODE`
  作用：控制是否启用本地 Telegram Bot API 模式，默认 `1`
  - `1`：使用本地模式，相当于 `Bot(token=TOKEN, local_mode=True, base_url=..., base_file_url=...)`
  - `0`：关闭本地模式，相当于 `Bot(token=TOKEN)`

### 3. 平台配置文件

平台公共配置在 [config/platforms.toml](./config/platforms.toml)。

当前包含：

- 下载根目录
- 公共请求头
- 各平台基础 URL
- 各平台 Cookie 文件名

这个文件会在 `core.settings` 导入时读取一次，其他模块直接使用已加载的常量，不会反复做配置文件 IO。

### 4. Cookie 文件

项目依赖本地 Cookie 文件，请将对应文件放到 `cookies/` 目录：

- 微博：`cookies/johnjohn01.txt`
- 抖音：`cookies/小号.txt`
- 抖音收藏：`cookies/大号.txt`
- Instagram：`cookies/neverblock11.txt`
- Bilibili：`cookies/bl.txt`

如果 Cookie 失效，抓取可能失败、返回空数据或被风控。

## 下载目录约定

默认下载根目录来自 `config/platforms.toml`：

```toml
[paths]
download_root = "/root/download"
```

也可以通过环境变量 `DOWNLOAD_ROOT` 覆盖。

当前目录规则统一为：

- 媒体文件：`<DOWNLOAD_ROOT>/<platform>/<username>/<filename>`
- JSON 文件：`<DOWNLOAD_ROOT>/<platform>/json/<username>/<filename>`

例如：

```text
/root/download/weibo/some_user/20260320_xxx.jpg
/root/download/bilibili/json/some_user/123456.info.json
```

## 运行方式

### 查看主入口帮助

```bash
python main.py --help
```

### 查看某个平台帮助

```bash
python main.py weibo --help
python main.py douyin --help
python main.py instagram --help
python main.py bilibili --help
```

也可以直接运行平台脚本：

```bash
python platforms/weibo.py --help
python platforms/douyin.py --help
python platforms/instagram.py --help
python platforms/bilibili.py --help
```

### 常用命令

抓取某个平台：

```bash
python main.py weibo
python main.py douyin
python main.py instagram
python main.py bilibili
```

使用 Bilibili 别名：

```bash
python main.py bili
```

推荐使用的简写：

```bash
python main.py weibo -u 糕 -S
python main.py -u 糕 -S -s latest_time:asc
python main.py weibo -slt
python main.py weibo -slt "2024-01-01 00:00:00"
python main.py -i 123456
python main.py -n favorite
python main.py -v 1 2
python main.py -j
```

只抓取和下载，不发送 Telegram：

```bash
python main.py weibo --no-send
```

关闭下载进度条：

```bash
python main.py bilibili --no-download-progress
```

从本地 JSON 回放：

```bash
python main.py weibo --local-json
python main.py instagram --local-json
```

按用户筛选：

```bash
python main.py weibo -i 123456
python main.py douyin -n favorite
python main.py weibo -u 糕
python main.py -u 糕
```

只查看筛中的用户，不执行爬取和发送：

```bash
python main.py weibo -S -u 糕
python main.py -S -u 糕
python main.py -S -v 1 2
```

自定义排序：

```bash
python main.py -S -u 糕 -s latest_time:asc
python main.py -S -s username:asc
python main.py -S -s valid:desc
```

覆盖 `latest_time`，强制多抓历史内容：

```bash
python main.py weibo -slt
python main.py weibo -slt "2024-01-01 00:00:00"
python main.py -S -u 糕 -slt
```

按关注类型筛选：

```bash
python main.py instagram -v 1
python main.py bilibili -v 1 2
```

按时间窗口筛选：

```bash
python main.py weibo --lts "2026-03-01 00:00:00"
python main.py weibo --lte "2026-03-15 23:59:59"
python main.py douyin --sts "2026-03-01 00:00:00"
```

### 公共 CLI 参数

各平台统一支持以下参数：

- `-v` / `--valid`
- `-i` / `--uid` / `--user-id`
- `-n` / `--name` / `--username`
- `-u` / `--user` / `--uname`
- `--lts` / `--latest-time-start`
- `--lte` / `--latest-time-end`
- `--sts` / `--scrapy-time-start`
- `--ste` / `--scrapy-time-end`
- `-s` / `--sort`
- `-slt` / `--set-latest-time`
- `-S` / `--show`
- `-N` / `--no-send`
- `-p` / `--progress` / `--download-progress`
- `-j` / `--json` / `--local-json`

说明：

- `platform` 现在是可选参数
- 省略 `platform` 时，会先从 `user` 表筛选命中的记录，再按其中的 `platform` 自动分发到对应平台执行
- `--sort` 格式是 `字段[:asc|desc]`，默认 `scrapy_time:desc`
- `-slt` / `--set-latest-time` 会临时覆盖本次运行中所有用户的 `latest_time`
- `--show` 只展示筛中的 `user` 记录，不执行爬取、下载、发送和数据库回写
- 旧参数名仍然可用，短参数只是更推荐的写法
- `-slt` 不带值，或传空字符串时，会使用 `2000-12-12 12:12:12`

### `--valid` 取值

- `-2`：用户已失效 / 被平台删除
- `-1`：不再关注
- `0`：取消关注
- `1`：特别关注
- `2`：普通关注

### `--sort` 支持字段

- `scrapy_time`
- `latest_time`
- `username`
- `userid`
- `platform`
- `valid`

也兼容这些别名：

- `scrapy-time`
- `latest-time`
- `user-id`
- `user_id`

### `--show` 展示说明

- 单平台 `--show`：展示当前平台筛中的用户
- 不传 `platform` 的 `--show`：展示跨平台结果，并额外显示平台列
- 如果终端支持 OSC 8 超链接，表格里的 `用户ID` / `用户名` 可以点击打开主页

## Telegram 发送说明

当前发送逻辑默认连接本地 Telegram Bot API Server，而不是直接使用公网默认地址。

## 日志说明

- 抓取流程日志会同时输出到控制台和平台日志文件
- 下载完成日志会显示在进度条控制台区域，同时额外写入对应平台日志文件
- 下载完成日志不会再通过普通 `logger.info()` 回显到控制台，避免和 Rich 进度条重复输出

如果你不想走本地模式，可以设置：

```env
TELEGRAM_LOCAL_MODE=0
```

此时会退回官方默认模式，相当于直接使用 `Bot(token=TOKEN)`。

固定地址在 [core/sender_dispatcher.py](./core/sender_dispatcher.py)：

- `http://localhost:8081/bot`
- `http://localhost:8081/file/bot`

这意味着运行前需要满足以下条件之一：

- 你已经部署并启动了本地 Bot API Server
- 或者你自行修改发送器中的 `base_url` / `base_file_url`

## 数据库说明

项目主要依赖两个表：

### `user`

用于保存关注对象，主流程至少依赖这些字段：

- `userid`
- `username`
- `platform`
- `valid`
- `latest_time`
- `scrapy_time`

其中：

- `platform`：`weibo` / `douyin` / `instagram` / `bilibili`
- `valid`
  - `0`：取消关注
  - `1`：特别关注
  - `2`：普通关注

### `messages`

用于保存发送结果和去重信息。代码中当前主要使用字段包括：

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

## 日志与错误

日志目录默认是 `logs/`。

当前主要文件：

- 平台日志：`logs/scrapy_<platform>.log`
- 发送日志：`logs/send.log`
- 错误日志：`logs/error.txt`

## `ops/` 脚本说明

`ops/` 下的脚本不是主抓取入口，更多是个人运维和历史修复工具：

- [ops/manage.py](./ops/manage.py)
  Telegram 管理脚本
- [ops/nicefuturebot.py](./ops/nicefuturebot.py)
  较早期的 Telegram 交互脚本
- [ops/deal_error.py](./ops/deal_error.py)
  失败记录重试
- [ops/chat_download.py](./ops/chat_download.py)
  从 Telegram 历史回拉媒体
- [ops/modify_msg.py](./ops/modify_msg.py)
  批量修改已发送消息

这些脚本很多都带有真实副作用，例如：

- 直接连接 Telegram
- 直接读写本地文件
- 直接轮询 bot

使用前建议先阅读代码并确认其中的本地路径、Token、聊天 ID 和运行环境假设。

## 当前推荐关注的代码入口

如果你只关心主抓取链路，优先看这些文件：

- [main.py](./main.py)
- [platforms/__init__.py](./platforms/__init__.py)
- [platforms/weibo.py](./platforms/weibo.py)
- [platforms/douyin.py](./platforms/douyin.py)
- [platforms/instagram.py](./platforms/instagram.py)
- [platforms/bilibili.py](./platforms/bilibili.py)
- [core/models.py](./core/models.py)
- [core/scrapy_runner.py](./core/scrapy_runner.py)
- [core/downloader.py](./core/downloader.py)
- [core/sender_dispatcher.py](./core/sender_dispatcher.py)
- [core/database.py](./core/database.py)
- [core/settings.py](./core/settings.py)

## 当前状态

目前主抓取入口已经整理为统一架构：

- 4 个平台都基于 `BasePlatform` / `BasePost`
- 公共 CLI 参数已经统一
- 下载目录和 JSON 目录已经统一
- 下载进度条已经接入公共下载器
- Bilibili 视频下载走 `yt-dlp`
- 配置文件已经集中到 `config/platforms.toml`

## 注意事项

- 项目高度依赖各平台登录 Cookie
- Telegram 发送默认依赖本地 Bot API Server，但可通过 `TELEGRAM_LOCAL_MODE=0` 关闭
- `ops/` 脚本偏个人化，运行前先检查
- Windows 终端里某些中文帮助文本可能出现编码显示问题，但不影响主入口运行
