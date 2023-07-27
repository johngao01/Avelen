create table if not exists messages
(
    MESSAGE_ID     TEXT,
    CAPTION        TEXT,
    CHAT_ID        TEXT,
    DATE_TIME      TEXT,
    FORM_USER      TEXT,
    CHAT           TEXT,
    MEDIA_GROUP_ID TEXT,
    weibo_url      TEXT,
    TEXT_RAW       TEXT
);

create table if not exists photo
(
    file_id        TEXT,
    file_unique_id TEXT,
    width          TEXT,
    height         TEXT,
    file_size      TEXT,
    file_name      TEXT,
    message_id     TEXT,
    media_group_id TEXT,
    weibo_url      TEXT
);

create table if not exists followings
(
    USERID          TEXT,
    USERNAME        TEXT,
    SCRAPY_TYPE     INTEGER default 0,
    LAST_WEIBO_TIME TEXT
);

create table if not exists video
(
    file_id        TEXT,
    file_unique_id TEXT,
    width          TEXT,
    height         TEXT,
    duration       integer,
    file_size      TEXT,
    file_name      TEXT,
    file_type      TEXT,
    message_id     TEXT,
    media_group_id TEXT,
    weibo_url      TEXT
);

create table if not exists document
(
    file_id        TEXT,
    file_unique_id TEXT,
    file_name      TEXT,
    file_type      TEXT,
    file_size      TEXT,
    message_id     TEXT,
    media_group_id TEXT,
    weibo_url      TEXT
);