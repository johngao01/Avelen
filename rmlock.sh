#!/bin/bash

# 设置程序的执行命令和日志文件路径
LOG_FILE="/root/pythonproject/weibo_tg_bot/scrapy_weibo.log"
# shellcheck disable=SC2034
LOCK_FILE="/root/pythonproject/weibo_tg_bot/start.lock"

# 定义函数来检查日志是否实时写入
function check_log_updated() {
    if [ -e $LOCK_FILE ];then
        # 获取日志文件的上次修改时间
      last_modification=$(stat -c %Y "$LOG_FILE")

      # 等待一段时间，让日志有时间更新
      sleep 90

      # 再次获取日志文件的修改时间
      current_modification=$(stat -c %Y "$LOG_FILE")
      echo "$current_modification" "$last_modification"
      # 比较两次修改时间，如果没有更新，则返回1，表示卡死
      if [ "$current_modification" -eq "$last_modification" ]; then
          return 1
      else
          return 0
      fi
    else
      echo "没有锁文件"
      sleep 90
      return 0
    fi

}

# 循环监控程序状态
while true; do
    # 启动爬虫程序
    # 检查日志是否更新，如果没有更新则杀死程序
    check_log_updated
    if [ $? -eq 1 ]; then
        echo "程序可能卡死，正在重启..."
#        pkill -f weibo_scrapy.py
        rm $LOG_FILE
    else
        echo "程序正常运行"
    fi
done

