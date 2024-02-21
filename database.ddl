CREATE TABLE "followings"
(
    USERID       TEXT
        constraint followings_pk
            primary key,
    USERNAME     TEXT,
    SCRAPY_TYPE  INTEGER default 0,
    LATEST_TIME  TEXT,
    douyin_weibo TEXT,
    scrapy_time  TEXT
)

CREATE TABLE "messages"
(
    MESSAGE_ID     INT,
    CAPTION        TEXT,
    CHAT_ID        TEXT,
    DATE_TIME      TEXT,
    FORM_USER      TEXT,
    CHAT           TEXT,
    MEDIA_GROUP_ID INT,
    TEXT_RAW       TEXT,
    URL            TEXT,
    USERID         TEXT,
    IDSTR          TEXT,
    MBLOGID        TEXT
)

CREATE TABLE "document"
(
    file_id        TEXT,
    file_unique_id TEXT,
    file_name      TEXT,
    file_type      TEXT,
    file_size      INT,
    message_id     INT
        constraint document_messages_MESSAGE_ID_fk
            references messages (MESSAGE_ID),
    media_group_id INT,
    url            TEXT
);

CREATE TABLE "photo"
(
    file_id        TEXT,
    file_unique_id TEXT,
    width          TEXT,
    height         TEXT,
    file_size      TEXT,
    file_name      TEXT,
    message_id     INT
        constraint photo_messages_MESSAGE_ID_fk
            references messages (MESSAGE_ID),
    media_group_id INT,
    url            TEXT
);

CREATE TABLE "video"
(
    file_id        TEXT,
    file_unique_id TEXT,
    width          TEXT,
    height         TEXT,
    duration       integer,
    file_size      TEXT,
    file_name      TEXT,
    file_type      TEXT,
    message_id     INT
        constraint video_messages_MESSAGE_ID_fk
            references messages (MESSAGE_ID),
    media_group_id INT,
    url            TEXT
);

