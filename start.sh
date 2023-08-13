#!/bin/bash
# shellcheck disable=SC2034
script_dir="$(dirname "$0")"
LOCKFILE="${script_dir}/start.lock"

# 检查是否有其他实例正在运行
if [ -f "$LOCKFILE" ]; then
  echo "Script is already running. Exiting."
  exit 1
fi

# 创建锁文件
touch "$LOCKFILE"

# 在这里执行你的任务
cd "${script_dir}" || exit
python3 weibo_scrapy.py
# 删除锁文件
rm "$LOCKFILE"
