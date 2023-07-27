#!/bin/bash

# 查找所有Python 3进程并保存其PID到一个数组
# shellcheck disable=SC2207
pids=($(pgrep -f "python3"))

if [ ${#pids[@]} -eq 0 ]; then
  echo "No Python3 processes found."
else
  echo "Killing Python3 processes..."
  # 使用循环逐个杀死进程
  for pid in "${pids[@]}"; do
    echo "Killing process with PID: $pid"
    kill "$pid"
  done
  echo "All Python3 processes killed."
fi

rm -rf  __pycache__ 