#!/bin/bash
# shellcheck disable=SC2034
script_dir="$(dirname "$0")"

# 在这里执行你的任务
cd "${script_dir}" || exit
timeout 600s python3 weibo_scrapy.py