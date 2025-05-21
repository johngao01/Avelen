CREATE DATABASE nicebot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE nicebot;

CREATE TABLE `user`
(
    `USERID`       VARCHAR(255) NOT NULL,
    `USERNAME`     VARCHAR(255),
    `latest_time`  VARCHAR(255),
    `douyin_weibo` VARCHAR(255),
    `scrapy_time`  VARCHAR(255),
    PRIMARY KEY (`USERID`)
) CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE `messages`
(
    `MESSAGE_ID`     INT,
    `CAPTION`        TEXT,
    `CHAT_ID`        VARCHAR(255),
    `DATE_TIME`      VARCHAR(255),
    `FORM_USER`      VARCHAR(255),
    `CHAT`           TEXT,
    `MEDIA_GROUP_ID` VARCHAR(100),
    `TEXT_RAW`       TEXT,
    `URL`            VARCHAR(255),
    `USERID`         VARCHAR(255),
    `IDSTR`          VARCHAR(255),
    `MBLOGID`        VARCHAR(255),
    PRIMARY KEY (`MESSAGE_ID`)
) CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE `document`
(
    `file_id`        VARCHAR(255),
    `file_unique_id` VARCHAR(255),
    `file_name`      VARCHAR(255),
    `file_type`      VARCHAR(255),
    `file_size`      INT,
    `message_id`     INT,
    `media_group_id` VARCHAR(100),
    `url`            VARCHAR(255)
) CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE `photo`
(
    `file_id`        VARCHAR(255),
    `file_unique_id` VARCHAR(255),
    `width`          VARCHAR(255),
    `height`         VARCHAR(255),
    `file_size`      VARCHAR(255),
    `file_name`      VARCHAR(255),
    `message_id`     INT,
    `media_group_id` VARCHAR(100),
    `url`            VARCHAR(255)
) CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

CREATE TABLE `video`
(
    `file_id`        VARCHAR(255),
    `file_unique_id` VARCHAR(255),
    `width`          VARCHAR(255),
    `height`         VARCHAR(255),
    `duration`       INT,
    `file_size`      VARCHAR(255),
    `file_name`      VARCHAR(255),
    `file_type`      VARCHAR(255),
    `message_id`     INT,
    `media_group_id` VARCHAR(100),
    `url`            VARCHAR(255)
) CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;
